# ①view/*
<br>
フロントアプリ(vue)

# ②flask/whisper_api_request.py<br>
バックエンドAPI
<br>
ー指定IDの低レゾTSファイルをDL・DB(request_operation_listテーブル)登録API<br>
ー映像ファイルが存在するかチェックAPI<br>
ー結果送信先のメールアドレス追加API<br>
ー処理中のファイルの残時間取得API<br>

# ③folder_watch/watch_ts_req.py
<br>
DB登録されたIDの低レゾTSファイルをDL・DB更新<br>

# ④whisper_req.py
<br>
ーTSファイルをfaster-whisperにより文字起こし<br>
ーTSファイルからスタートタイムコードを取得<br>
ー文字起こし結果と各タイムコードをrequest_operation_listテーブルのIDと紐づいた、
　request_transcriptionsテーブルに登録<br>
ーTSファイルをhtml5プレーヤーで再生できるようmp4ファイルに変換<br>
ー各文字起こし結果はMeCabで形態素解析し、文末表現まで文字起こし結果をつなげる<br>
ーja以外はDeepLで翻訳結果を付与<br>



# ◯その他メモ<br>
ーモデルは↓から自動更新でDLしようとする。model_pathにこのモデルのパスを指定するとローカルで完結。<br>
 https://huggingface.co/guillaumekln<br>

ーlarge-v3使うには：↑はv2までしかない。パスを↓に変えるもしくはローカルにモデルDLでv3使用可能<br>
https://github.com/SYSTRAN/faster-whisper<br>

# ファイル版参考サイト<br>
https://github.com/PINTO0309/faster-whisper-env<br>
https://github.com/guillaumekln/faster-whisper<br>

# リアルタイム版参考サイト<br>
https://qiita.com/reriiasu/items/dccffb249a41959c839e

