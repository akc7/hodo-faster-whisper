import psycopg2
import time
import os
import requests
import json
import logging
import signal
import subprocess
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel
import gc,torch
from concurrent.futures import ThreadPoolExecutor, as_completed
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import MeCab

# ログ設定
logging.basicConfig(filename='/home/akashi/faster-whisper/log/whisper_req_ope.log', level=logging.INFO)
DEEPL_API_URL = "https://api.deepl.com/v2/translate"
API_KEY = "api-key"
 
# DB接続設定
try:
    conn = psycopg2.connect(
        dbname="whisper",
        user="postgres",
        password="****",
        host="localhost"
    )
    cur = conn.cursor()
except Exception as e:
    logging.error(f"Database connection failed: {e}")
    exit()

# テーブルがなければ作成
try:
    cur.execute("""
    CREATE TABLE IF NOT EXISTS request_operation_list (
        id SERIAL PRIMARY KEY,
        status VARCHAR(10) NOT NULL,
        file_code CHAR(5) NOT NULL,
        file_path VARCHAR(128)[],
        added_time TIMESTAMP NOT NULL,
        watch_date CHAR(8) NOT NULL,
        translated_time TIMESTAMP,
        email VARCHAR(255)[]
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS request_transcriptions (
        id SERIAL PRIMARY KEY,
        session_id INT NOT NULL,
        start_time VARCHAR(8) NOT NULL,
        end_time VARCHAR(8) NOT NULL,
        text TEXT NOT NULL,
        multi_id INT NOT NULL,
        initial_time VARCHAR(8) NOT NULL,
        video_duration VARCHAR(8)
    );
    """)
    conn.commit()
except Exception as e:
    logging.error(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - Table creation failed: {e}")
    exit()
finally:
    cur.close()
    conn.close()


# faster-whisper API URL
# API_URL = "http://etc02958:5000/predict"

def seconds_to_timecode(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

def timecode_to_seconds(timecode):
    hours, minutes, seconds_frames = timecode.split(':')
    seconds = seconds_frames.split(';')[0]  # フレーム数を無視
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)

def extract_timecode(ts_file):
    cmd = ['ffprobe', '-show_frames', '-pretty', '-read_intervals', '%+#1', '-loglevel', 'quiet', '-i', ts_file]
    output = subprocess.check_output(cmd).decode('utf-8')
    pattern = r'TAG:timecode=([^\n]+)'
    timecode_matches = re.findall(pattern, output)
    # 文字列を時間の形式に変換
    time_format = "%H:%M:%S:%f"
    time_obj = datetime.strptime(timecode_matches[0].replace(";",":"), time_format)

    # 1フレーム引いた時間を計算
    one_frame = timedelta(milliseconds=1000 / 100)
    new_time_obj = time_obj - one_frame

    # 新しい時間を文字列に変換
    new_time_str = new_time_obj.strftime(time_format)

    return new_time_str[:8]

def get_video_duration(file_path):
    cmd = f'ffprobe -i {file_path} -show_entries format=duration -v quiet -of csv="p=0"'
    output = subprocess.check_output(cmd, shell=True).decode('utf-8')
    return float(output.strip())

def insert_and_commit(record, segments, start_tc_seconds):
    logging.info(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - insert_and_commit_start {record[0]} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")

    local_conn = psycopg2.connect(
        dbname="whisper",
        user="postgres",
        password="****",
        host="localhost"
    )
    local_cur = local_conn.cursor()
    try:
        insert_data = [(record[0], seconds_to_timecode(segment.start + start_tc_seconds),
                        seconds_to_timecode(segment.end + start_tc_seconds), segment.text) for segment in segments]
        local_cur.executemany("""
                        INSERT INTO request_transcriptions (session_id, start_time, end_time, text)
                        VALUES (%s, %s, %s, %s)
                        """, insert_data)
        local_conn.commit()
        print("DB_end: "+str(record[0])+ "---" +time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
    except Exception as e:
        logging.error(f"Error occurred while inserting and committing: {e}")
    finally:
        logging.info(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - insert_and_commit_end {record[0]} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
        local_cur.close()
        local_conn.close()

def sendmail(subject, body, mail_to):
    gmail_account = "A-VAboo <A-VAboo@tv-asahi.co.jp>"
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = gmail_account
    msg["To"] = mail_to
    msg.attach(MIMEText(body, "html"))

    s = smtplib.SMTP("fuga", 25,timeout=10)
    s.starttls()
    s.sendmail(gmail_account, mail_to, msg.as_string())
    s.quit()

def transcode_ts_to_mp4(file_paths):
    # Sort the file paths to ensure they are concatenated in the correct order
    file_paths.sort()

    # Create a temporary file list for ffmpeg
    temp_file_list = "/home/akashi/faster-whisper/temp_file_list.txt"
    with open(temp_file_list, 'w') as f:
        for file_path in file_paths:
            f.write(f"file '{file_path}'\n")

    # Determine the output file name
    base_name = os.path.splitext(file_paths[0])[0]
    output_file_path = f"{base_name}.mp4"

    # Run ffmpeg command to concatenate and transcode
    cmd = [
        'ffmpeg', '-y', 
        '-f', 'concat', '-safe', '0', '-i', temp_file_list,
        '-c:v', 'h264_nvenc',
        '-ac', '2',  # Convert audio to stereo
        '-loglevel', 'quiet',
        output_file_path
    ]
    subprocess.run(cmd)

    # Remove the temporary file list
    os.remove(temp_file_list)

# def translate_to_japanese(text):
#     print(text)
#     payload = {
#         "text": text,
#         "target_lang": "JA",
#         "auth_key": API_KEY,
#     }
    
#     try:
#         response = requests.post(DEEPL_API_URL, data=payload)
#         # print(response.status_code)
#         print(response.json())

#         # if response.status_code != 200:
#         #     raise Exception(f"DeepL API request failed with status code {response.status_code}: {response.text}")
        
#         translation_result = response.json()
#         translated_text = translation_result['translations'][0]['text']
#         return translated_text

#     except Exception as e:
#         logging.error(f"Error DeepL occurred: {e}")
#         return ""


def translate_to_japanese(text):
    print(text)
    # print(type(text))
    try:
        headers = {
            'Authorization': 'DeepL-Auth-Key '+ API_KEY,
            'Content-Type': 'application/json',
        }

        data = {
            "text": [
                text
            ],
            "target_lang": "JA"
        }

        response = requests.post(DEEPL_API_URL, headers=headers, data=json.dumps(data))
        translation_result = response.json()
        # print(translation_result)
        translated_text = translation_result['translations'][0]['text']
        return translated_text
    
    except Exception as e:
        logging.error(f"Error DeepL occurred: {e}")
        return ""

def is_sentence_end(text):
    tagger = MeCab.Tagger("")
    words = tagger.parse(text).split("\n")
    last_word_info = words[-3].split("\t")
    if "終止形-一般" in last_word_info or "補助記号-句点" in last_word_info:
        return True
    return False




last_execution_time = datetime.now() - timedelta(hours=2)

while True:
    try:
        app = Flask(__name__)

        current_time = datetime.now()
        time_diff = current_time - last_execution_time

        print(time_diff.total_seconds())
        if time_diff.total_seconds() > 3600:  # Check if more than 1 hour has passed
            if 'model' in locals():
                del model
                gc.collect()
                torch.cuda.empty_cache()

            # モデルを初期化
            # model_size = "large-v1"
            # model_size = "large-v2"
            # model_size = "medium"
            # model_size = "tiny"
            model_size = "/home/akashi/faster-whisper/model_archive_large-v2_20230815"
            model = WhisperModel(model_size, device="cuda", compute_type="float32")

            last_execution_time = current_time  # Update the last execution time


        conn = psycopg2.connect(
            dbname="whisper",
            user="postgres",
            password="****",
            host="localhost"
        )
        cur = conn.cursor()

        cur.execute("SELECT * FROM request_operation_list WHERE status = 'translate' ORDER BY added_time ASC;")
        records = cur.fetchall()

        cur.close()
        conn.close()

        # with ThreadPoolExecutor(max_workers=2) as executor:
        #     futures = []
        for record in records:
            try:
                file_paths = record[3]  # 変更点: 順番に合わせてインデックスを修正

                if not file_paths:
                    conn = psycopg2.connect(
                        dbname="whisper",
                        user="postgres",
                        password="****",
                        host="localhost"
                    )
                    cur = conn.cursor()
                    cur.execute("UPDATE request_operation_list SET status = 'failed' WHERE id = %s", (record[0],))
                    conn.commit()
                    cur.close()
                    conn.close()

                    if record[7]:
                        error_mail_to_list = '; '.join(record[7])  # Convert list of emails to comma-separated string
                        print("mail_send")
                        error_body = """
                            <html>
                            <head> """+"</head>" +f"""
                            <body style="font-family: 'Yu Gothic', sans-serif; font-size: 11pt;">
                                <p>文字起こしに失敗しました。<br><br>送信した素材ID<"""+ record[2] +""">は指定の日にち"""+ record[5] +"""に存在しませんでした。再度ご確認ください。</p>
                            </body>
                            </html>
                            """
                        sendmail("【A-VAboo】文字起こし失敗", error_body, error_mail_to_list)

                    break

                # ファイルサイズが5秒間変わらないか確認
                initial_sizes = {file_path: os.path.getsize(file_path) for file_path in file_paths}
                time.sleep(5)
                for file_path in file_paths:
                    final_size = os.path.getsize(file_path)

                    if initial_sizes[file_path] != final_size:
                        break
                
                else:
                    print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) + "ffmpeg start: " + ', '.join(file_paths))
                    logging.info(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) + "ffmpeg start: " + ', '.join(file_paths))

                    transcode_ts_to_mp4(file_paths)
                    print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) + "ffmpeg end")
                    logging.info(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) + "ffmpeg end")

                    conn = psycopg2.connect(
                        dbname="whisper",
                        user="postgres",
                        password="****",
                        host="localhost"
                    )
                    cur = conn.cursor()

                    total_video_duration = 0  # 初期値を0に設定

                    for index, file_path in enumerate(file_paths):

                        video_duration = get_video_duration(file_path)
                        print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) + "start: "+str(video_duration)+ "---" +file_path)
                        logging.info(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) + "start: "+str(video_duration)+ "---" +file_path)
                        
                        # Set the status based on video duration
                        new_status = 'completed'
                        # if video_duration <= 15:
                        #     new_status = 'done_short'
                        start_tc = extract_timecode(file_path)
                        start_tc_seconds = timecode_to_seconds(start_tc)

                        # モデルで推論
                        segments, info = model.transcribe(file_path, beam_size=5)
                        print(f"Detected language {info.language} with probability {info.language_probability:.2f}")

                        # Update transcription_sessions
                        # cur.execute("""
                        # INSERT INTO transcription_sessions (session_id, watch_date, file_code, language, language_probability)
                        # VALUES (%s, %s, %s, %s, %s)
                        # """, (record[0], record[5], record[2], info.language, info.language_probability))

                        print("DB_start: "+str(record[0])+ "---" +time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
                        # print(video_duration > 1800)
                        # print(futures)
                        # if video_duration > 1800:
                        #     futures.append(executor.submit(insert_and_commit, record, segments, start_tc_seconds))
                        # else:


                        # insert_data = [(record[0], seconds_to_timecode(segment.start + start_tc_seconds), seconds_to_timecode(segment.end + start_tc_seconds), segment.text, index, seconds_to_timecode(start_tc_seconds), seconds_to_timecode(total_video_duration)) for segment in segments]



                        insert_data = []
                        if info.language != "ja" and info.language_probability > 0.80:

                            if info.language=="zh":
                                segments = list(segments)
                                for segment in segments:
                                    print(segment.text)
                                    translated_text = translate_to_japanese(segment.text)
                                    insert_data.append((record[0], seconds_to_timecode(segment.start + start_tc_seconds), seconds_to_timecode(segment.end + start_tc_seconds), segment.text + "\n" + translated_text, index, seconds_to_timecode(start_tc_seconds), seconds_to_timecode(total_video_duration)))

                            else:
                                segments = list(segments)
                                combined_text = ""
                                segment_start_tc_seconds = None  # 結合したテキストの最初のsegment.start
                                for seg_num, segment in enumerate(segments):
                                    if segment_start_tc_seconds==None:
                                        segment_start_tc_seconds = segments[seg_num].start

                                    print(segment.text)
                                    if segment.text.endswith("."):
                                        combined_text += segment.text
                                        translated_text = translate_to_japanese(combined_text)
                                        insert_data.append((record[0], seconds_to_timecode(segment_start_tc_seconds + start_tc_seconds), seconds_to_timecode(segment.end + start_tc_seconds), combined_text + "\n" + translated_text, index, seconds_to_timecode(start_tc_seconds), seconds_to_timecode(total_video_duration)))
                                        combined_text = ""
                                        segment_start_tc_seconds = None
                                    else:
                                        combined_text += segment.text
                        else:
                            # info.languageが"JA"であるか、info.language_probabilityが0.85以下の場合
                            if info.language=="ja":
                                segments = list(segments)
                                combined_text = ""
                                segment_start_tc_seconds = None  # 結合したテキストの最初のsegment.start
                                for seg_num, segment in enumerate(segments):
                                    if segment_start_tc_seconds==None:
                                        segment_start_tc_seconds = segments[seg_num].start

                                    combined_text += segment.text + " "  # 末尾に半角スペースを追加

                                    # 次のsegmentの開始時刻と現在のsegmentの終了時刻の差を計算
                                    time_difference = (segments[seg_num + 1].start if seg_num + 1 < len(segments) else segment.end) - segment.end
                                    

                                    # print(combined_text)
                                    # print(is_sentence_end(combined_text))
                                    
                                    # 文末の判定または時間の差の判定
                                    if is_sentence_end(combined_text) or time_difference >= 3 or seg_num + 1 == len(segments):
                                        insert_data.append((record[0], seconds_to_timecode(segment_start_tc_seconds + start_tc_seconds), seconds_to_timecode(segment.end + start_tc_seconds), combined_text, index, seconds_to_timecode(start_tc_seconds), seconds_to_timecode(total_video_duration)))
                                        combined_text = ""
                                        segment_start_tc_seconds = None
                            else:
                                insert_data = [(record[0], seconds_to_timecode(segment.start + start_tc_seconds), seconds_to_timecode(segment.end + start_tc_seconds), segment.text, index, seconds_to_timecode(start_tc_seconds), seconds_to_timecode(total_video_duration)) for segment in segments]

                        print(insert_data)


                        cur.executemany("""
                        INSERT INTO request_transcriptions (session_id, start_time, end_time, text, multi_id, initial_time, video_duration)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, insert_data)
                        print("DB_end: "+str(record[0])+ "---" +time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))


                        # Update request_operation_list
                        cur.execute("""
                        UPDATE request_operation_list
                        SET status = %s, translated_time = %s
                        WHERE id = %s
                        """, (new_status, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()), record[0]))
                            
                        conn.commit()

                        if record[7]:
                            mail_to_list = '; '.join(record[7])  # Convert list of emails to comma-separated string
                            print("mail_send")
                            body = """
                                <html>
                                <head> """+"</head>" +f"""
                                <body style="font-family: 'Yu Gothic', sans-serif; font-size: 11pt;">
                                    <p>文字起こしが完了しました。<br><br>文字起こし結果↓<br>
                                    <a href="http://etc02958/AI-VAboo/?file_code=""" + str(record[2]) + "&watch_date=" + str(record[5]) + """">http://etc02958/AI-VAboo/?file_code=""" + str(record[2]) + "&watch_date=" + str(record[5]) + """</a><br><br>
                                    ご質問やご要望等あればNT班(内線1548)までご連絡ください。</p>
                                </body>
                                </html>
                                """
                            sendmail("【A-VAboo】文字起こし完了", body, mail_to_list)

                        logging.info(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - translated file {file_path} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")

                        total_video_duration += video_duration  # 合計に追加
                        # os.remove(file_path)

                    cur.close()
                    conn.close()

            except Exception as e:
                logging.error(f"Error occurred while processing record {record[0]} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}: {e}")

            # for future in as_completed(futures):
            #     try:
            #         future.result()
            #     except Exception as e:
            #         logging.error(f"An exception was raised: {e}")


        # conn = psycopg2.connect(
        #     dbname="whisper",
        #     user="postgres",
        #     password="****",
        #     host="localhost"
        # )
        # cur = conn.cursor()

        # # Update waiting items if older than 10 minutes
        # cur.execute("SELECT * FROM request_operation_list WHERE status = 'waiting';")
        # waiting_records = cur.fetchall()
        # current_time = time.time()
        # for record in waiting_records:
        #     time_diff = current_time - time.mktime(time.strptime(str(record[6]), '%Y-%m-%d %H:%M:%S'))
        #     if time_diff >= 600:  # 10 minutes
        #         cur.execute("""
        #         UPDATE request_operation_list
        #         SET status = 'processing'
        #         WHERE id = %s
        #         """, (record[0],))

        # conn.commit()
        # cur.close()
        # conn.close()

    except Exception as e:
        logging.error(f"Error occurred: {e}")
        
    time.sleep(5)  # 15-second interval
