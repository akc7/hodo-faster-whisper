import psycopg2
from smb.SMBConnection import SMBConnection
import os
import time
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(filename='/home/akashi/faster-whisper/log/ts_smb_watcher.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('smbprotocol').setLevel(logging.WARNING)

db_params = {
    "dbname":"whisper",
    "user":"postgres",
    "password":"****",
    "host":"localhost"
}

while True:
    try:
        conn = psycopg2.connect(**db_params)
        cur = conn.cursor()
        
        # Fetch records with status "processing"
        cur.execute("SELECT * FROM request_operation_list WHERE status='processing'")
        records = cur.fetchall()

        for record in records:
            watch_date = record[5]
            file_code = record[2]

            # Define SMB connection and path based on watch_date and file_code
            smb_conn = SMBConnection("proxy", "hoge", "etc02958", "10.208.69.22", use_ntlm_v2=True)
            smb_conn.connect("10.208.69.22", 139)
            remote_dir = f"/news/{watch_date[:6]}/{watch_date[-4:]}/"
            local_dir = "/home/akashi/faster-whisper/tmp_req/"
            # print(remote_dir)
            try:
                files = smb_conn.listPath('proxy', remote_dir)
                files = sorted(files, key=lambda f: f.create_time)
                ts_files = [f for f in files if file_code in f.filename and f.filename.endswith('.ts')]

                # Get initial sizes for all ts files
                initial_sizes = {}
                for ts_file in ts_files:
                    remote_path = os.path.join(remote_dir, ts_file.filename)
                    initial_sizes[ts_file.filename] = smb_conn.getAttributes('proxy', remote_path).file_size

                # Wait for 10 seconds
                time.sleep(10)

                # Check for size changes
                all_files_same_size = True
                for ts_file in ts_files:
                    remote_path = os.path.join(remote_dir, ts_file.filename)
                    new_size = smb_conn.getAttributes('proxy', remote_path).file_size

                    if initial_sizes[ts_file.filename] != new_size:
                        all_files_same_size = False
                        cur.execute("UPDATE request_operation_list SET status='growing', translated_time=%s WHERE id=%s", (datetime.now(), record[0]))
                        conn.commit()
                        break

                if all_files_same_size:
                    copied_files = []
                    # Copy files and update database
                    for ts_file in ts_files:
                        remote_path = os.path.join(remote_dir, ts_file.filename)
                        local_path = os.path.join(local_dir, ts_file.filename)

                        # Copy file
                        with open(local_path, 'wb') as f:
                            smb_conn.retrieveFile('proxy', remote_path, f)

                        copied_files.append(local_path)

                    # Update database
                    cur.execute("UPDATE request_operation_list SET status='translate', file_path=%s WHERE id=%s", (copied_files, record[0]))
                    conn.commit()
                    logging.info(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - New file {file_code} added to PostgreSQL.")
                        

            except Exception as e:
                logging.error(f"An error occurred: {e}")

            smb_conn.close()

        # Check for 'growing' records and update them if needed
        cur.execute("SELECT * FROM request_operation_list WHERE status='growing'")
        growing_records = cur.fetchall()

        for record in growing_records:
            translated_time = record[6]
            if translated_time and (datetime.now() - translated_time) > timedelta(minutes=1):
                cur.execute("UPDATE request_operation_list SET status='processing', translated_time=NULL WHERE id=%s", (record[0],))
                conn.commit()

        cur.close()
        conn.close()
    
    except IndexError as ie:
        cur.close()
        conn.close()
        if file_code :
            logging.error(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - Index error at file {file_code}: {ie}")
        else:
            logging.error(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - Index error at file : {ie}")

    except Exception as e:
        cur.close()
        conn.close()
        if file_code :
            logging.error(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - Failed to process file : {e}")
        else:
            logging.error(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - Failed to process file {file_code}: {e}")


    time.sleep(15)  # wait for 1 minute before checking again
