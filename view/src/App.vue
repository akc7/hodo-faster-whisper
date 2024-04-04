<template>
  <div id="app">
    <header :class="['header', isCentered ? 'centered' : '']">
      <div class="header-content">
        <h1 style="margin-right: 20px;">A-VAboo</h1>
        <span style="margin-top: 20px;">by</span>
        <img src="logo.png" alt="NewsTechnology" class="header-image" />
      </div>
      <div class="input-group">
        <label for="materialId">素材ID：</label>
        <input v-model="file_code" type="text" id="materialId" placeholder="例) 1R111" class="input-materialId" @keyup.enter="fetchAndMove" @input="convertToHalfWidth">
        <label for="date">入稿日：</label>
        <input v-model="watch_date" type="date" id="date" class="input-date">
        <button @click="fetchAndMove" :disabled="isFetching">確認</button>
      </div>
    </header>


    <div v-if="isCentered && minutesDataFetched" class="minutes-data-section">
      <h2 v-if="minutesData.length > 0">終了時間の目安</h2>
      <h2 v-else>待ち時間：0分</h2>
      <ul class="minutes-list">
        <li v-for="(item, index) in minutesData" :key="index" class="minutes-item">
          <span class="item-number">{{ item.result_number }}</span>
          <span class="file-code">{{ item.file_code }}</span>
          <span class="result-time">{{ item.result }}</span>
        </li>
      </ul>
    </div>

    <div v-if="isFetching" class="loading-indicator">
      ロード中...
    </div>



    <div v-if="result === 'done' && isCentered == false">
      <video 
        ref="videoPlayer" 
        :src="videoSrc" 
        controls oncontextmenu="return false;"
        controlsList="nodownload" 
        width="320" 
        height="240" 
        style="position: fixed; top: -16px; right: 10px;"
      >
        お使いのブラウザは映像をサポートしていません。
      </video>
      <div class="transcriptions">
        <button @click="copyAllText">全てコピー</button>
        <div v-for="dataItem in data" :key="dataItem.session_id">
        <button 
          class="time-button" 
          @click="jumpToTime(dataItem.start_time, dataItem.multi_id, dataItem.initial_time, dataItem.video_duration)" 
          :aria-label="'Jump to ' + dataItem.start_time"
        >
        【{{ dataItem.start_time }}】
        </button>
        <p v-html="dataItem.text.split('\n').join('<br>')"></p>
        </div>
      </div>
    </div>


    <div v-if="showModal" class="modal">
      <div class="modal-content">
        <p v-html="modalMessage"></p>
        <input v-if="showEmailInput" v-model="email" type="email" name="userEmail" id="userEmail" placeholder="メールアドレスを入力" autocomplete="on" class="input-email">
        <button v-if="showEmailInput" @click="submitEmail" class="email-submit">送信</button>
        <button @click="closeModal" class="close-button">閉じる</button>
      </div>
    </div>

    <div v-if="showShortModal" class="modal">
      <div class="modal-content">
        <h2 class="short-modal">{{ shortModalMessage }}</h2>
      </div>
    </div>
  </div>
</template>


<script>
import axios from 'axios';

export default {
  data() {
    return {
      file_code: '',
      watch_date: '',
      email: '',
      result: '',
      data: [],
      file_path: [], // 映像ファイルのパスを保持するための配列
      isCentered: true,
      showModal: false,
      modalMessage: '',
      showEmailInput: false,
      showShortModal: false, // 短時間モーダルの表示状態を制御
      shortModalMessage: '',  // 短時間モーダルのメッセージ
      videoSrc: '', // 追加: MP4ファイルのURLを保持するためのデータプロパティ
      isFetching: false, // 追加: API呼び出し中かどうかを追跡するためのフラグ
      minutesData: [], // APIから取得したデータを格納
      minutesDataFetched: false, // APIからデータを取得したかどうかを示すフラグ
    };
  },
  mounted() {
    const urlParams = new URLSearchParams(window.location.search);
    const fileCode = urlParams.get('file_code');
    const watchDate = urlParams.get('watch_date');
    
    if (fileCode && watchDate) {
      this.file_code = fileCode;
      this.watch_date = watchDate;
      this.fetchAndMove();
    }else {
      this.getMinutesData();
    }

    this.pollingInterval = setInterval(() => {
      this.getMinutesData();
    }, 10000); // 10秒ごとに更新

  },
  beforeUnmount() {
    // コンポーネントが破棄される前にポーリングを停止
    clearInterval(this.pollingInterval);
  },
  watch: {
    file_path: {
      immediate: true,
      handler(newVal) {
        if (newVal && newVal[0]) {
          // .tsファイルのURLを.mp4に変換して、videoSrcにセットします。
          this.videoSrc = newVal[0].replace("/home/akashi/faster-whisper/tmp_req", "http://etc02958/tmp_req").replace(".ts", ".mp4");
        }
      }
    },
    result(newVal) {
      if (newVal === 'growing' || newVal === 'translating') {
        this.openModal('<h2 style="color: #fc9d32;">文字起こし中<br>少々お待ちください</h2>終わり次第、メールで結果が欲しい場合は<br>メールアドレスを入力して送信してください', true);
      } else if (newVal === 'added') {
        this.openModal('<h2 style="color: #008fdf;">文字起こしを開始しました<br>少々お待ちください</h2>終わり次第、メールで結果が欲しい場合は<br>メールアドレスを入力して送信してください', true);
      } else if (newVal === 'done') {
        this.isCentered = false;
      }
    },
    file_code(newVal) {
      if (newVal && newVal.length === 5) {
        const today = new Date();
        let lastDateWithNumber = today;

        while (lastDateWithNumber.getDate().toString().slice(-1) !== newVal[0]) {
          lastDateWithNumber.setDate(lastDateWithNumber.getDate() - 1);
        }

        const year = lastDateWithNumber.getFullYear();
        const month = (lastDateWithNumber.getMonth() + 1).toString().padStart(2, '0');
        const date = lastDateWithNumber.getDate().toString().padStart(2, '0');

        this.watch_date = `${year}-${month}-${date}`;
      }
    }
  },
  methods: {
    jumpToTime(timeString, multi_id, initial_time, video_duration) {
      // timeStringから秒数を算出
      const timeParts = timeString.split(':').map(Number);
      const seconds = timeParts[0] * 3600 + timeParts[1] * 60 + timeParts[2];
      
      // initial_timeから秒数を算出
      const initialTimeParts = initial_time.split(':').map(Number);
      const initialSeconds = initialTimeParts[0] * 3600 + initialTimeParts[1] * 60 + initialTimeParts[2];

      let offsetTime;
      
      if (multi_id === 0) {
          // multi_idが0のとき
          offsetTime = seconds - initialSeconds;
      } else if (multi_id >= 1) {
          // multi_idが1以上のとき
          offsetTime = (seconds - initialSeconds) + video_duration;
      }

      // videoのcurrentTimeを更新して再生位置をジャンプさせる
      this.$refs.videoPlayer.currentTime = offsetTime;

      if (this.$refs.videoPlayer.paused) {
        this.$refs.videoPlayer.play();
      }

    },
    async checkFileExists() {
      const url = 'http://etc02958:5000/api/check_file';
      const payload = {
        file_code: this.file_code,
        watch_date: this.watch_date.replace(/-/g,"")
      };
      try {
        const response = await axios.post(url, payload);
        if (response.data.exists) {
          await this.fetchData();
        } else {
          this.openModal('<h2 style="color: #e63c60;">存在しない素材IDと入稿日の組み合わせです<br>再度入力してください</h2>');
        }
      } catch (error) {
        console.error('API call failed', error);
        this.openModal('<h2 style="color: #e63c60;">システムが混み合っています<br>時間を空けて再度お試しください</h2>');
      }
    },
    async fetchData() {
      const url = 'http://etc02958:5000/api/post_data';
      const payload = {
        file_code: this.file_code,
        watch_date: this.watch_date.replace(/-/g,"")
      };
      try {
        const response = await axios.post(url, payload);
        this.result = 'temp-value';
        this.$nextTick(() => {
          this.result = response.data.result;
        });
        this.data = response.data.data || [];
        this.file_path = response.data.file_path || []; // 映像ファイルのパスをセット
        console.log(this.result);
        // console.log(this.isCentered);
        // console.log(this.showModal);
        
      } catch (error) {
        console.error('API call failed', error);
      }
    },
    // async fetchAndMove() {
    //   if (!/^[A-Za-z0-9]{5}$/.test(this.file_code)) {
    //     this.openModal('素材IDは5桁の英数字で入力してください。例) 1R111');
    //     return;
    //   }

    //   await this.checkFileExists();
    // },
    async fetchAndMove() {
      if (this.isFetching) return; // 既にフェッチ中の場合は何もしない
      
      if (!/^[A-Za-z0-9]{5}$/.test(this.file_code)) {
        this.openModal('素材IDは5桁の英数字で入力してください。例) 1R111');
        return;
      }

      this.isFetching = true; // フェッチ開始前にフラグを設定
      try {
        await this.checkFileExists();
        // ...他の処理
      } catch (error) {
        console.error('API call failed', error);
      } finally {
        this.isFetching = false; // 処理が完了したらフラグをリセット
      }
    },
    convertToHalfWidth() {
      this.file_code = this.file_code.replace(/[０-９Ａ-Ｚａ-ｚ]/g, function(s) {
        return String.fromCharCode(s.charCodeAt(0) - 0xFEE0);
      });
    },
    copyAllText() {
      const textToCopy = this.data.map(dataItem => `【${dataItem.start_time}】 ${dataItem.text}`).join('\n');

      // 一時的なテキストエリアを生成
      const textArea = document.createElement('textarea');
      textArea.value = textToCopy;
      document.body.appendChild(textArea);
      
      // テキストエリアを選択
      textArea.select();
      
      // テキストをクリップボードにコピー
      document.execCommand('copy');

      // 一時的なテキストエリアを削除
      document.body.removeChild(textArea);
      this.showShortModalMessage('コピーしました');
    },
    showShortModalMessage(message) {
      this.shortModalMessage = message;
      this.showShortModal = true;
      setTimeout(() => {
        this.showShortModal = false;
        this.shortModalMessage = '';
      }, 1500);  // 2秒後にモーダルを非表示にする
    },

    async submitEmail() {
      const url = 'http://etc02958:5000/api/update_email'; // Updated URL
      const payload = {
        email: this.email,
        file_code: this.file_code,
        watch_date: this.watch_date.replace(/-/g,"")
      };
      try {
        await axios.post(url, payload);
        console.log('Email updated successfully');
        this.modalMessage = '<h3 style="color: #008fdf;">メールアドレスを登録しました</h3>文字起こしが終了次第メールでお知らせします';
        this.showModal = true;
        this.showEmailInput = false;
      } catch (error) {
        console.error('Failed to update email', error);
      }
    },
    getMinutesData() {
      const url = 'http://etc02958:5000/api/get_minutes'; // Updated URL
      axios.get(url)
      .then(response => {
        this.minutesData = response.data;
        this.minutesDataFetched = true; // データ取得後にフラグを設定
      })
      .catch(error => {
        console.error("There was an error fetching the minutes data:", error);
      });

    },
    openModal(message, showEmail = false) {
      this.modalMessage = message;
      this.showModal = true;
      this.showEmailInput = showEmail;
      // this.isCentered = false;
    },
    closeModal() {
      this.modalMessage = '';
      this.showModal = false;
      this.showEmailInput = false;
      this.isCentered = true;
      this.getMinutesData();

    }

  }
};
</script>


<style scoped>
#app {
  text-align: center;
  padding: 0;
  margin: 20px;
  font-family: Arial, sans-serif;
  color: #333;
  background-color: #eef2ff;
  position: relative;
  min-height: 95vh; /* Ensure the background color covers the whole viewport */
}

.header {
  background: rgba(255, 255, 255, 0.95);
  padding: 0 20px;
  border-radius: 10px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 100%;
  transition: transform 0.7s cubic-bezier(0.68, -0.55, 0.27, 1.55), top 0.5s;
}

.header h1 {
  color: #5a6eb2;
  font-size: 2.5em;
  margin-bottom: 20px;
}

.header.centered {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  max-width: 500px;
}

.header:not(.centered) {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  max-width: 600px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
  background: #dce6f8;
  padding: 15px;
  border-radius: 10px;
}

.header:not(.centered) .input-group {
  flex-direction: row;
  align-items: center;
  justify-content: space-around;
}

.input-date, .input-materialId {
  padding: 10px;
  border: none;
  border-radius: 5px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
  color: #333;
  flex: 1;
}

button {
  padding: 10px 20px;
  font-size: 26px;
  color: #fff;
  background-color: #99b0fd;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

button:hover {
  background-color: #7a8fd8;
}

.transcriptions {
  margin-top: 234px;
  text-align: left;
  padding: 20px;
  border-radius: 5px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

h2 {
  margin-bottom: 10px;
}

p {
  margin-bottom: 20px;
}

.info-box {
  margin-top: 220px; /* Adjust this value as needed to position .info-box below the header */
}



.info-box input.input-email {
  padding: 10px;
  border: 2px solid #5a6eb2;
  border-radius: 5px;
  margin-top: 10px;
}

.info-box button.email-submit {
  padding: 10px 20px;
  font-size: 16px;
  color: #5a6eb2;
  background-color: #eef2ff;
  border: 2px solid #5a6eb2;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.3s ease;
  margin-top: 10px;
}

.modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  color: #fff;
  font-size: 24px;
  transition: opacity 0.3s ease;
}

.modal-content {
  background-color: #fff;
  padding: 20px;
  border-radius: 10px;
  width: 80%;
  max-width: 600px;
  text-align: center;
  transform: scale(0.7);
  transition: transform 0.3s cubic-bezier(0.68, -0.55, 0.27, 1.55);
  color: #333;
}

.modal.show {
  opacity: 1;
}
.modal.show .modal-content {
  transform: scale(1);
}
.input-email {
  margin-top: 10px;
  padding: 10px;
  border-radius: 5px;
  border: 1px solid #ccc;
  width: 90%;
  font-size: 24px;
}
.email-submit {
  margin-top: 10px;
  /* padding: 10px; */
  color: #fff;
  background-color: #99b0fd;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.3s ease;
  margin-right: 20px;
}
.email-submit:hover {
  background-color: #7a8fd8;
}
.close-button {
  margin-top: 20px;
  display: inline-block;
}


.short-modal{
  font-size: 2.5em;
  margin-bottom : 45px;
}

.time-button {
  background: none;
  border: none;
  color: blue;
  text-decoration: underline;
  cursor: pointer;
  font-size: 1.2em; /* 必要に応じてサイズを調整 */
  padding: 0;
}

.time-button:hover,
.time-button:focus {
  color: darkblue;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-image {
  max-height: 65px; /* 画像のサイズを調整 */
  margin-top: 15px;
  padding-left: 5px;
}


.minutes-data-section {
  padding: 0 20px;
  background-color: #f0f0f0;
  border-radius: 10px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
  position: absolute; /* 絶対位置指定 */
  top: calc(50% + 200px); /* ヘッダーの高さを考慮して位置を調整 */
  left: 50%;
  transform: translateX(-50%);
  width: 100%; /* 必要に応じて幅を調整 */
  max-width: 500px; /* ヘッダーと同じ最大幅を設定 */
}


.minutes-data-section h2 {
  margin-bottom: 15px;
}

.minutes-data-section ul {
  list-style-type: none;
  background-color: #ffffff; /* 要素の背景色は適宜調整 */
  border-radius: 5px;
  padding: 0;
}

.minutes-data-section li {
  padding: 10px;
}

.minutes-item {
  display: flex;
  align-items: center;
}


.minutes-list {
  list-style-type: none;
  padding: 0;
}

.list-item {
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.item-number {
  font-weight: bold;
  color: #5a6eb2;
  margin-right: 25px;
  margin-left: 25%;
  width: 30px; /* 項番の幅を固定 */
}

.file-code {
  margin-right: 10px;
  width: 80px; /* file_codeの幅を固定 */
}

.loading-indicator {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background-color: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 20px;
  border-radius: 10px;
  font-size: 1.5em;
}



</style>