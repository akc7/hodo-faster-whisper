①view/*
フロントアプリ(vue)

②flask/whisper_api_request.py
バックエンドAPI
ー指定IDの低レゾTSファイルをDL・DB(request_operation_listテーブル)登録API
ー映像ファイルが存在するかチェックAPI
ー結果送信先のメールアドレス追加API
ー処理中のファイルの残時間取得API

③folder_watch/watch_ts_req.py
DB登録されたIDの低レゾTSファイルをDL・DB更新

④whisper_req.py
ーTSファイルをfaster-whisperにより文字起こし
ーTSファイルからスタートタイムコードを取得
ー文字起こし結果と各タイムコードをrequest_operation_listテーブルのIDと紐づいた、
　request_transcriptionsテーブルに登録
ーTSファイルをhtml5プレーヤーで再生できるようmp4ファイルに変換
ー各文字起こし結果はMeCabで形態素解析し、文末表現まで文字起こし結果をつなげる
ーja以外はDeepLで翻訳結果を付与


◯その他メモ
ーモデルは↓から自動更新でDLしようとする。model_pathにこのモデルのパスを指定するとローカルで完結。 https://huggingface.co/guillaumekln
ーlarge-v3使うには：↑はv2までしかない。パスを↓に変えるもしくはローカルにモデルDLでv3使用可能
https://github.com/SYSTRAN/faster-whisper

ファイル版参考サイト
https://github.com/PINTO0309/faster-whisper-env
https://github.com/guillaumekln/faster-whisper
リアルタイム版参考サイト
https://qiita.com/reriiasu/items/dccffb249a41959c839e

