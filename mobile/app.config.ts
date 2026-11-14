import type {ExpoConfig} from 'expo/config';
const localDevelopment = process.env.CZON_MOBILE_LAN === '1';
const config: ExpoConfig = {
  name: 'CzON Agent', slug: 'czon-agent-mobile', version: '0.1.0',
  userInterfaceStyle: 'light', orientation: 'default',
  icon: './assets/icon.png',
  ios: {
    bundleIdentifier: process.env.CZON_IOS_BUNDLE_ID || 'cn.czon.agent.mobile', supportsTablet: true,
    infoPlist: {
      NSLocalNetworkUsageDescription: '连接您在局域网中运行的 CzON Agent 服务。',
      ITSAppUsesNonExemptEncryption: false,
      NSAppTransportSecurity: {NSAllowsArbitraryLoads: localDevelopment},
    },
  },
  android: {package: 'cn.czon.agent.mobile', softwareKeyboardLayoutMode: 'resize'},
  plugins: [
    ['expo-audio', {microphonePermission: '使用麦克风将您的语音转成任务文字。', enableBackgroundRecording: false, enableBackgroundPlayback: false}],
    'expo-secure-store', 'expo-document-picker',
  ],
};
export default config;
