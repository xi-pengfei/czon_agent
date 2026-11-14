export type Language = 'zh-CN' | 'zh-TW' | 'en';
export const languages: Language[] = ['zh-CN', 'zh-TW', 'en'];
export const languageNames = {'zh-CN': '简体中文', 'zh-TW': '繁體中文', en: 'English'};
const strings = {
  offlineLogout: ['已退出本机；服务器会话暂未撤销，将按原有策略过期。','已登出本機；伺服器工作階段暫未撤銷，將按原有政策到期。','Signed out locally. The server session could not be revoked and will expire normally.'],
  agent: ['AI智能体','AI智慧體','AI assistant'], login: ['登录','登入','Sign in'], server: ['服务地址','服務位址','Server URL'],
  account: ['账号','帳號','Account'], password: ['密码','密碼','Password'], logout: ['退出登录','登出','Sign out'],
  welcome: ['Hi，我是你的工作助手','Hi，我是你的工作助手','Hi, I’m your work assistant'],
  tagline: ['查数据、整理文件，一起把工作做好。','查資料、整理檔案，一起把工作做好。','Explore data, organize files, get work done.'],
  task: ['新任务','新任務','New task'], sessions: ['最近任务','最近任務','Recent tasks'], settings: ['设置','設定','Settings'],
  placeholder: ['输入任务，输入 / 选择技能','輸入任務，輸入 / 選擇技能','Describe a task, type / for skills'],
  skills: ['选择技能','選擇技能','Choose a skill'], search: ['搜索技能名称或用途','搜尋技能名稱或用途','Search skills'],
  files: ['添加文件','加入檔案','Add file'], model: ['选择模型','選擇模型','Choose a model'], noModel: ['暂无可用模型，请联系管理员','暫無可用模型，請聯絡管理員','No models available. Contact your administrator.'],
  send: ['发送','傳送','Send'], stop: ['停止任务','停止任務','Stop task'], cancel: ['取消','取消','Cancel'], close: ['关闭','關閉','Close'],
  record: ['开始录音','開始錄音','Record'], finish: ['结束录音','結束錄音','Finish recording'], transcribing: ['正在识别…','正在辨識…','Transcribing…'],
  recording: ['正在录音','正在錄音','Recording'], micDenied: ['请在系统设置中允许使用麦克风','請在系統設定中允許使用麥克風','Allow microphone access in system settings'],
  reconnect: ['连接中，任务仍在后台继续','連線中，任務仍在背景繼續','Connecting. Tasks continue on the server.'],
  queued: ['排队中','排隊中','Queued'], working: ['正在处理任务','正在處理任務','Working on your task'], done: ['已完成','已完成','Completed'],
  stopped: ['已停止','已停止','Stopped'], failed: ['任务未完成','任務未完成','Task did not finish'],
  play: ['播放语音摘要','播放語音摘要','Play spoken summary'], stopAudio: ['停止播放','停止播放','Stop playback'],
  confirm: ['确认执行','確認執行','Confirm operation'], confirmTitle: ['请确认业务操作','請確認業務操作','Review operation'],
  change: ['修改密码','修改密碼','Change password'], oldPassword: ['原密码','原密碼','Current password'], newPassword: ['新密码（至少 6 位）','新密碼（至少 6 位）','New password (6+ characters)'],
  changeRequired: ['请先修改初始密码','請先修改初始密碼','Change your initial password to continue'],
  empty: ['暂无任务','暫無任務','No tasks yet'], error: ['提示','提示','Notice'], retry: ['重试发送','重試傳送','Retry sending'],
  pending: ['发送结果尚未确认，请重试；不会重复创建任务。','傳送結果尚未確認，請重試；不會重複建立任務。','Delivery not confirmed. Retry safely without creating a duplicate task.'],
  unavailable: ['管理员尚未配置语音服务','管理員尚未設定語音服務','Speech service is not configured'],
  add: ['添加','加入','Add'], language: ['界面语言','介面語言','Interface language'], remove: ['移除','移除','Remove'],
  historyError: ['历史记录加载失败，请重新打开任务','歷史記錄載入失敗，請重新開啟任務','Could not load history. Reopen this task.'],
} as const;
export type StringKey = keyof typeof strings;
export const translator = (language: Language) => (key: StringKey): string => strings[key][languages.indexOf(language)];
