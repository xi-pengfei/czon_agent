import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import {StatusBar} from 'expo-status-bar';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import {Client, login, restoreCredentials, saveCredentials, type Credentials} from './src/client';
import {Button, styles, colors} from './src/ui';
import {languageNames, languages, translator, type Language} from './src/strings';
import {Workspace} from './src/Workspace';

// 部署地址由构建环境提供；未配置时由用户输入。
const DEFAULT_SERVER =
  process.env.EXPO_PUBLIC_CZON_SERVER ||
  Constants.expoConfig?.extra?.defaultServer ||
  '';

export default function App() {
  const [auth, setAuth] = useState<Credentials | null>(null), [ready, setReady] = useState(false);
  const [language, setLanguage] = useState<Language>('zh-CN');
  const [address, setAddress] = useState(DEFAULT_SERVER), [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const t = translator(language);
  const expired = useCallback(() => { setAuth(null); void saveCredentials(null); }, []);
  const client = useMemo(() => auth ? new Client(auth, expired) : null, [auth, expired]);
  useEffect(() => { void (async () => {
    try {
      const savedLanguage = await SecureStore.getItemAsync('czon.mobile.language');
      if (languages.includes(savedLanguage as Language)) setLanguage(savedLanguage as Language);
      const savedAddress = await SecureStore.getItemAsync('czon.mobile.server'); if (savedAddress) setAddress(savedAddress);
      const saved = await restoreCredentials();
      if (saved) {
        // Keep the stored session on transient network failure, but never on explicit revocation.
        const candidate = new Client(saved, () => {});
        try { saved.identity = await candidate.get('/api/me', AbortSignal.timeout(15_000)); setAuth(saved); }
        catch (e) { if ((e as {status?: number}).status === 401) await saveCredentials(null); else setAuth(saved); }
      }
    } catch (e) { setError((e as Error).message); }
    finally { setReady(true); }
  })(); }, []);
  async function changeLanguage(next: Language) { setLanguage(next); await SecureStore.setItemAsync('czon.mobile.language', next); }
  async function signIn() {
    setBusy(true); setError('');
    try {
      const value = await login(address, username.trim(), password);
      await saveCredentials(value); await SecureStore.setItemAsync('czon.mobile.server', value.origin);
      setAuth(value); setPassword('');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function changePassword() {
    if (!client || !auth) return;
    setBusy(true); setError('');
    try {
      const data = await client.post<Credentials['identity'] & {session_token: string}>('/api/auth/change-password', {old_password: password, new_password: newPassword});
      const {session_token, ...identity} = data;
      const value = {...auth, identity, token: session_token}; await saveCredentials(value); setAuth(value); setPassword(''); setNewPassword('');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function logout() {
    if (!client) return;
    try { await client.response('/api/auth/logout', {method: 'POST', body: '{}', signal: AbortSignal.timeout(5000)}); }
    catch { Alert.alert(t('error'), t('offlineLogout')); }
    finally { expired(); }
  }
  return <SafeAreaProvider><SafeAreaView style={styles.root}><StatusBar style="dark"/>
    {!ready ? <ActivityIndicator style={{flex: 1}}/> : auth && client && !auth.identity.must_change_password ?
      <Workspace key={`${auth.origin}:${auth.token}`} client={client} language={language} changeLanguage={changeLanguage} logout={logout}/> :
      <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{flexGrow: 1, justifyContent: 'center', padding: 28, width: '100%', maxWidth: 480, alignSelf: 'center'}}>
          <Text style={{fontSize: 30, fontWeight: '700', color: colors.ink, marginBottom: 8}}>czon<Text style={{color: colors.blue}}>.cn</Text></Text>
          <Text style={[styles.muted, {marginBottom: 32}]}>{auth ? t('changeRequired') : t('tagline')}</Text>
          {!auth && <><Text style={styles.label}>{t('server')}</Text><TextInput accessibilityLabel={t('server')} style={styles.input} value={address} onChangeText={setAddress} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="https://agent.example.com"/>
            <Text style={styles.label}>{t('account')}</Text><TextInput accessibilityLabel={t('account')} style={styles.input} value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} autoComplete="username"/></>}
          <Text style={styles.label}>{auth ? t('oldPassword') : t('password')}</Text><TextInput accessibilityLabel={t('password')} style={styles.input} value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password"/>
          {auth && <><Text style={styles.label}>{t('newPassword')}</Text><TextInput accessibilityLabel={t('newPassword')} style={styles.input} value={newPassword} onChangeText={setNewPassword} secureTextEntry autoComplete="new-password"/></>}
          {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
          <Button title={busy ? '…' : auth ? t('change') : t('login')} disabled={busy || !password || (auth ? newPassword.length < 6 : !address || !username)} onPress={() => void (auth ? changePassword() : signIn())}/>
          {auth && <Button title={t('logout')} onPress={() => void logout()}/>}
          <View style={{flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', marginTop: 20}}>{languages.map(l => <Text accessibilityRole="button" key={l} onPress={() => void changeLanguage(l)} style={{padding: 12, color: l === language ? colors.blue : colors.muted}}>{languageNames[l]}</Text>)}</View>
        </ScrollView>
      </KeyboardAvoidingView>}
  </SafeAreaView></SafeAreaProvider>;
}
