from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime, timedelta
import logging
from smb.SMBConnection import SMBConnection
from flask_cors import CORS  # flask-corsを追加
import subprocess

app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "http://etc02958"}})

logging.basicConfig(filename='/home/akashi/faster-whisper/log/request_api.log', level=logging.INFO)
logging.getLogger("SMB.SMBConnection").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Database connection settings
db_params = {
    "dbname":"whisper",
    "user":"postgres",
    "password":"****",
    "host":"localhost"
}

try:

    # Create tables if they don't exist
    conn = psycopg2.connect(**db_params)
    cur = conn.cursor()

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
    cur.close()
    conn.close()
    logging.info("Tables created successfully.")
except Exception as e:
    logging.error(f"Error while creating tables: {e}")


def get_video_duration(file_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        duration = float(result.stdout)
        return duration
    except Exception as e:
        logging.error(f"Error getting video duration: {e}")
        return 0


@app.route('/api/post_data', methods=['POST'])
def post_data():
    try:
        data = request.json
        file_code = data.get('file_code')
        watch_date = data.get('watch_date')

        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()

        cur.execute("SELECT * FROM request_operation_list WHERE file_code=%s AND watch_date=%s ORDER BY id DESC LIMIT 1", (file_code, watch_date))
        existing_record = cur.fetchone()

        print(existing_record)

        if existing_record:
            if existing_record[1] == 'completed':
                cur.execute("SELECT * FROM request_transcriptions WHERE session_id=%s ORDER BY id", (existing_record[0],))
                transcriptions = cur.fetchall()
                results = [
                    {
                        "session_id": t[1],
                        "start_time": t[2],
                        "end_time": t[3],
                        "text": t[4],
                        "multi_id": t[5],
                        "initial_time": t[6],
                        "video_duration": t[7]
                    }
                    for t in transcriptions
                ]
                logging.info(f"Returning completed data for file_code={file_code}, watch_date={watch_date}.")
                cur.close()
                conn.close()
                return jsonify({"result": "done", "data": results, "file_path": existing_record[3]})

            elif existing_record[1] == 'growing':
                logging.info(f"Status is growing for file_code={file_code}, watch_date={watch_date}.")
                cur.close()
                conn.close()
                return jsonify({"result": "growing"})

            elif existing_record[1] == 'translate' or existing_record[1] == 'processing' :
                logging.info(f"translating file_code={file_code}, watch_date={watch_date}.")
                cur.close()
                conn.close()
                return jsonify({"result": "translating"})

        else:
            cur.execute("""
            INSERT INTO request_operation_list (status, file_code, watch_date, added_time) VALUES (%s, %s, %s, %s) RETURNING id
            """, ('processing', file_code, watch_date, datetime.now()))
            inserted_id = cur.fetchone()[0]  # Get the returned ID
            conn.commit()
            logging.info(f"Added new record with ID={inserted_id} for file_code={file_code}, watch_date={watch_date}.")
            cur.close()
            conn.close()
            return jsonify({"result": "added", "inserted_id": inserted_id})

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({"result": "error", "message": str(e)})

    return jsonify({"result": "error", "message": "Unexpected error occurred."})


@app.route('/api/check_file', methods=['POST'])
def check_file_exists():
    try:
        data = request.json
        file_code = data.get('file_code')
        watch_date = data.get('watch_date')
        
        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()
        cur.execute("SELECT * FROM request_operation_list WHERE file_code=%s AND watch_date=%s ORDER BY id DESC LIMIT 1", (file_code, watch_date))
        existing_record = cur.fetchone()

        cur.close()
        conn.close()        

        if existing_record:
            return jsonify({"exists": True})
        else:
            smb_conn = SMBConnection("proxy", "hoge", "etc02958", "10.208.69.22", use_ntlm_v2=True)
            smb_conn.connect("10.208.69.22", 139)
            remote_dir = f"/news/{watch_date[:6]}/{watch_date[-4:]}/"
            files = smb_conn.listPath('proxy', remote_dir)  # replace 'share_name' with the appropriate share name
            for file in files:
                if file.filename.endswith('.ts') and file_code in file.filename:
                    return jsonify({"exists": True})
            return jsonify({"exists": False})
        
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({"result": "error", "message": str(e)})

@app.route('/api/update_email', methods=['POST'])
def update_email():
    try:
        data = request.json
        email = data.get('email')
        file_code = data.get('file_code')
        watch_date = data.get('watch_date')
        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()
        cur.execute("SELECT email FROM request_operation_list WHERE file_code=%s AND watch_date=%s", (file_code, watch_date))
        existing_emails = cur.fetchone()
        if existing_emails:
            existing_emails = list(existing_emails[0]) if existing_emails[0] else []
            if email not in existing_emails:
                existing_emails.append(email)
            cur.execute("UPDATE request_operation_list SET email=%s WHERE file_code=%s AND watch_date=%s", (existing_emails, file_code, watch_date))
            conn.commit()
        cur.close()
        conn.close()
        return jsonify({"result": "success"})
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({"result": "error", "message": str(e)})

@app.route('/api/get_minutes', methods=['GET'])
def get_minutes():
    try:
        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()

        # 最低限の内容を取得する
        cur.execute("SELECT id, status, file_path, added_time, watch_date, file_code FROM request_operation_list WHERE status IN ('processing', 'translate') ORDER BY id")
        records = cur.fetchall()

        results = []
        last_result = None
        processing_found = False
        result_counter = 1
        for record in records:
            id, status, file_paths, added_time, watch_date, file_code = record

            if status == 'processing':
                processing_found = True

            if processing_found:
                # 'processing' が出現した後は全て "計算中" を設定
                results.append({"result_number": result_counter, "watch_date": watch_date, "file_code": file_code, "result": "計算中"})
            elif status == 'translate':
                total_duration = sum(get_video_duration(path) for path in file_paths)
                additional_minutes = round(total_duration * 0.3475943000119935)
                result = (added_time + timedelta(seconds=additional_minutes)) if not last_result else (last_result + timedelta(seconds=additional_minutes))
                last_result = result
                if result.date() == datetime.now().date():
                    result_str = (result + timedelta(minutes=1)).strftime("%H:%M")
                else:
                    result_str = (result + timedelta(minutes=1)).strftime("%d日 %H:%M")
                # print(total_duration, additional_minutes, result, result_str)
                results.append({"result_number": result_counter, "watch_date": watch_date, "file_code": file_code, "result": str(result_str)+" ごろ"})

            result_counter += 1

        cur.close()
        conn.close()
        return jsonify(results)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({"result": "error", "message": str(e)})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
