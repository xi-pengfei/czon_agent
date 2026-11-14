import React, {useEffect, useMemo, useRef, useState} from 'react';
import {ActivityIndicator, Alert, FlatList, Image, Keyboard, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, Text, TextInput, View} from 'react-native';
import * as Crypto from 'expo-crypto';
import * as DocumentPicker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';
import {File, Paths} from 'expo-file-system';
import Markdown from 'react-native-markdown-display';
import {Client} from './client';
import {useRuns} from './useRuns';
import {isActive, type Run} from './runs';
import {useVoice} from './useVoice';
import type {Artifact, Attachment, Provider, Session, Skill} from './types';
import {Button, IconButton, Sheet, colors, styles} from './ui';
import {languageNames, languages, translator, type Language} from './strings';
const id = () => Crypto.randomUUID().replace(/-/g, '');
type Message = {id: string | number; role: string; content: string; run_id?: string; artifacts?: Artifact[]};
type MessageRow = {key: string; role: string; content: string; run?: Run; artifacts?: Artifact[]};
type Draft = {text: string; skill: Skill | null; attachments: Attachment[]};
const emptyDraft = (): Draft => ({text: '', skill: null, attachments: []});
export function Workspace({client, language, changeLanguage, logout}: {client: Client; language: Language; changeLanguage: (language: Language) => Promise<void>; logout: () => Promise<void>}) {
  const t = useMemo(() => translator(language), [language]);
  const {runs, connected, revision} = useRuns(client);
  const [sessionId, setSessionId] = useState(id), [sessions, setSessions] = useState<Session[]>([]);
  const [loaded, setLoaded] = useState<{sessionId: string; messages: Message[]; runs: Run[]} | null>(null);
  const history = loaded?.sessionId === sessionId ? loaded.messages : [];
  const historyRuns = loaded?.sessionId === sessionId ? loaded.runs : [];
  const [drafts, setDrafts] = useState<Record<string, Draft>>({}), [providers, setProviders] = useState<Provider[]>([]), [provider, setProvider] = useState('');
  const [skills, setSkills] = useState<Skill[]>([]), [search, setSearch] = useState('');
  const [panel, setPanel] = useState<'sessions' | 'settings' | 'add' | 'skills' | 'model' | null>(null);
  const [activity, setActivity] = useState({runId: '', text: ''});
  const [error, setError] = useState(''), [sendingSessions, setSendingSessions] = useState<Record<string, boolean>>({}), [uploading, setUploading] = useState(false);
  const [pending, setPending] = useState<Record<string, {text: string; attachments: Attachment[]; provider: string; session_id: string; run_id: string; skill: string | null}>>({});
  const list = useRef<React.ComponentRef<typeof FlatList<MessageRow>>>(null), follow = useRef(true), locks = useRef(new Set<string>());
  const draft = drafts[sessionId] || emptyDraft();
  const sending = !!sendingSessions[sessionId];
  function updateDraft(patch: Partial<Draft>, sid = sessionId) { setDrafts(old => ({...old, [sid]: {...(old[sid] || emptyDraft()), ...patch}})); }
  const recordSession = useRef(sessionId);
  const voice = useVoice(client, t, text => {
    const sid = recordSession.current;
    setDrafts(old => ({...old, [sid]: {...(old[sid] || emptyDraft()), text: `${old[sid]?.text || ''}${text}`}}));
  }, setError);
  const allRuns = {...Object.fromEntries(historyRuns.map(r => [r.id, r])), ...runs};
  const sessionRuns = Object.values(allRuns).filter(r => r.session_id === sessionId).sort((a, b) => a.created_at.localeCompare(b.created_at));
  const active = sessionRuns.find(isActive);
  const storedRunIds = new Set(history.map(m => m.run_id).filter(Boolean));
  const liveRuns = sessionRuns.filter(r => !storedRunIds.has(r.id));
  const pendingSend = pending[sessionId];
  const activeId = active?.id;
  useEffect(() => {
    if (!activeId || !connected) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const response = await client.response(`/api/runs/${activeId}/narration`, {
          method: 'POST', body: JSON.stringify({kind: 'activity'}), signal: controller.signal,
        });
        const data = await response.json();
        if (!controller.signal.aborted) setActivity({runId: activeId, text: data.text || ''});
      } catch { /* Public progress is optional; task streaming continues independently. */ }
      if (!controller.signal.aborted) timer = setTimeout(refresh, 20_000);
    };
    timer = setTimeout(refresh, 12_000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [activeId, connected, client]);
  useEffect(() => {
    let alive = true;
    Promise.all([client.get<Provider[]>('/api/providers'), client.get<{skills: Skill[]}>('/api/skills')]).then(([p, s]) => {
      if (!alive) return; setProviders(p); setProvider(p.find(x => x.configured)?.name || ''); setSkills(s.skills);
    }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [client]);
  useEffect(() => {
    let alive = true;
    client.get<{sessions: Session[]}>('/api/sessions').then(data => { if (alive) setSessions(data.sessions); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [client, revision]);
  useEffect(() => {
    const controller = new AbortController();
    client.get<{messages: Message[]; runs: Run[]}>(`/api/sessions/${sessionId}`, controller.signal).then(data => {
      if (!controller.signal.aborted) { setLoaded({sessionId, messages: data.messages, runs: data.runs}); }
    }).catch(e => { if (!controller.signal.aborted && e.status !== 404) setError(t('historyError')); });
    return () => controller.abort();
  }, [client, sessionId, t]);
  // A retry reuses the original run ID, so a lost HTTP response cannot duplicate a job.
  async function send() {
    if (locks.current.has(sessionId) || (!draft.text.trim() && !pendingSend) || !provider || active) return;
    locks.current.add(sessionId); setSendingSessions(old => ({...old, [sessionId]: true})); setError(''); Keyboard.dismiss(); follow.current = true;
    list.current?.scrollToEnd({animated: true});
    const sid = sessionId;
    const request = pendingSend || {text: draft.text.trim(), attachments: draft.attachments, provider, session_id: sid, run_id: id(), skill: draft.skill?.name || null};
    setPending(old => ({...old, [sid]: request}));
    try {
      await client.post('/api/runs', request);
      setPending(old => { const next = {...old}; delete next[sid]; return next; });
      updateDraft(emptyDraft(), sid);
    } catch (e) {
      const status = (e as {status?: number}).status;
      // Definitive validation/permission failures can be edited; uncertain transport failures keep their id.
      if (status && status >= 400 && status < 500 && status !== 409) setPending(old => { const next = {...old}; delete next[sid]; return next; });
      setError((e as Error).message);
    } finally { setSendingSessions(old => ({...old, [sid]: false})); locks.current.delete(sid); }
  }
  function selectSession(next: string) {
    voice.stopPlayback(); void voice.cancel().catch(() => {}); setSessionId(next); setPanel(null); setError(''); follow.current = true;
  }
  async function upload() {
    const sid = sessionId; setPanel(null); setUploading(true);
    try {
      const result = await DocumentPicker.getDocumentAsync({copyToCacheDirectory: true});
      if (result.canceled) return;
      const asset = result.assets[0];
      if ((drafts[sid]?.attachments.length || 0) >= 10) throw new Error('最多添加 10 个文件');
      if (asset.size && asset.size > 50 * 1024 * 1024) throw new Error('文件不能超过 50 MB');
      const file = new File(asset.uri);
      try {
        const form = new FormData(); form.append('file', file, asset.name);
        const response = await client.response('/api/upload', {method: 'POST', body: form});
        const data = await response.json();
        setDrafts(old => ({...old, [sid]: {...(old[sid] || emptyDraft()), attachments: [...(old[sid]?.attachments || []), data]}}));
      } finally { if (file.exists) file.delete(); }
    } catch (e) { setError((e as Error).message); } finally { setUploading(false); }
  }
  async function download(artifact: Artifact) {
    let file: File | undefined;
    try {
      const response = await client.response(artifact.download_url);
      const suffix = artifact.name.match(/\.[a-zA-Z0-9]{1,10}$/)?.[0] || '';
      file = new File(Paths.cache, `czon-${id()}${suffix}`); file.write(new Uint8Array(await response.arrayBuffer()));
      await Sharing.shareAsync(file.uri, {mimeType: artifact.mime, dialogTitle: artifact.name});
    } catch (e) { setError((e as Error).message); } finally { if (file?.exists) file.delete(); }
  }
  const artifactList = (artifacts: Artifact[] = []) => artifacts.map(a => <Pressable accessibilityRole="button" key={a.id} onPress={() => void download(a)} style={styles.item}><Text style={{color: colors.blue}}>↓ {a.name}</Text></Pressable>);
  function confirmations(run?: Run) {
    return run?.steps.flatMap(step => {
      const confirmation = (step.result as {meta?: {confirmation?: {id: string; reason?: string}}})?.meta?.confirmation;
      if (!confirmation) return [];
      return [<Button key={confirmation.id} title={t('confirm')} onPress={() => Alert.alert(t('confirmTitle'), `${confirmation.reason || ''}\n${JSON.stringify(step.args || {}, null, 2)}`, [
        {text: t('cancel'), style: 'cancel'}, {text: t('confirm'), onPress: () => { void client.post('/api/tool/confirm', {confirmation_id: confirmation.id}).catch(e => setError(e.message)); }},
      ])}/>];
    });
  }
  function userMessage(text: string, key: string) { return <View key={key} style={styles.bubble}><Text style={styles.muted}>{client.credentials.identity.username}</Text><Text selectable style={styles.text}>{text}</Text></View>; }
  function assistant(text: string, run: Run | undefined, key: string, artifacts?: Artifact[]) {
    return <View key={key} style={{marginVertical: 12}}>
      <View style={styles.row}><Image source={require('../assets/assistant-avatar.png')} style={styles.avatar}/><Text style={[styles.text, {fontWeight: '600'}]}>{t('agent')}</Text>
        {run?.status === 'completed' && <IconButton name={voice.playing ? 'stop-circle-outline' : 'volume-medium-outline'} label={voice.playing ? t('stopAudio') : t('play')} disabled={voice.recording.isRecording || voice.busy} onPress={() => voice.playing ? voice.stopPlayback() : void voice.play(run.id)}/>}</View>
      {!!text && <MarkdownContent text={text}/>}
      {run && isActive(run) && <View style={[styles.row, {paddingVertical: 10}]}><ActivityIndicator size="small" color={colors.blue}/><Text style={[styles.muted, {flex: 1}]}>{run.status === 'queued' ? t('queued') : (activity.runId === run.id ? activity.text : '') || t('working')}</Text></View>}
      {run && !isActive(run) && run.status !== 'completed' && <Text style={styles.muted}>{run.error || t(run.status === 'stopped' ? 'stopped' : 'failed')}</Text>}
      {confirmations(run)}{artifactList(artifacts || run?.artifacts)}
    </View>;
  }
  const rows = (items: {key: string; title: string; subtitle?: string; action: () => void}[]) => items.map(item => <Pressable key={item.key} accessibilityRole="button" onPress={item.action} style={({pressed}) => [styles.item, {opacity: pressed ? .5 : 1}]}><Text style={styles.text}>{item.title}</Text>{item.subtitle && <Text numberOfLines={2} style={styles.muted}>{item.subtitle}</Text>}</Pressable>);
  return <KeyboardAvoidingView style={styles.page} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <View style={[styles.row, styles.header]}><IconButton name="menu-outline" label={t('sessions')} onPress={() => setPanel('sessions')}/><Text style={styles.heading}>{t('agent')}</Text><IconButton name="add" label={t('task')} onPress={() => selectSession(id())}/><IconButton name="settings-outline" label={t('settings')} onPress={() => setPanel('settings')}/></View>
    {!connected && <Text style={[styles.muted, {paddingHorizontal: 16, paddingTop: 4}]}>{t('reconnect')}</Text>}
    <FlatList ref={list} keyboardShouldPersistTaps="handled" contentContainerStyle={{padding: 16, flexGrow: 1}}
      data={[
        ...history.map(m => ({key: `history-${m.id}`, role: m.role, content: m.content, run: m.run_id ? allRuns[m.run_id] : undefined, artifacts: m.artifacts})),
        ...liveRuns.flatMap(run => [{key: `${run.id}-user`, role: 'user', content: run.text}, {key: run.id, role: 'assistant', content: run.reply, run}]),
      ] as MessageRow[]}
      keyExtractor={item => item.key}
      renderItem={({item}) => item.role === 'user' ? userMessage(item.content, item.key) : assistant(item.content, item.run, item.key, item.artifacts)}
      initialNumToRender={12} windowSize={7}
      onScroll={e => { const {contentOffset, layoutMeasurement, contentSize} = e.nativeEvent; follow.current = contentOffset.y + layoutMeasurement.height >= contentSize.height - 80; }} scrollEventThrottle={100}
      onContentSizeChange={() => { if (follow.current) list.current?.scrollToEnd({animated: false}); }}
      ListEmptyComponent={<View style={styles.welcome}><Image source={require('../assets/assistant-avatar.png')} style={{width: 88, height: 106, marginBottom: 20}}/><Text style={[styles.text, {fontSize: 22, fontWeight: '600', marginBottom: 12}]}>{t('welcome')}</Text><Text style={styles.muted}>{t('tagline')}</Text></View>}
    />
    {!!error && <Text accessibilityRole="alert" style={styles.error} onPress={() => setError('')}>{error}</Text>}
    {!!pendingSend && !active && <Text style={[styles.muted, {paddingHorizontal: 16}]}>{t('pending')}</Text>}
    <View style={styles.composer}>
      {(draft.skill || draft.attachments.length > 0) && <ScrollView horizontal contentContainerStyle={{gap: 12, paddingHorizontal: 10}}>
        {draft.skill && <Pressable accessibilityLabel={t('remove')} onPress={() => updateDraft({skill: null})} style={styles.item}><Text style={{color: colors.blue}}>{draft.skill.display_name || draft.skill.name} ×</Text></Pressable>}
        {draft.attachments.map(a => <Pressable accessibilityLabel={t('remove')} key={a.path} style={styles.item} onPress={() => updateDraft({attachments: draft.attachments.filter(x => x.path !== a.path)})}><Text style={styles.muted}>{a.name} ×</Text></Pressable>)}
      </ScrollView>}
      {voice.recording.isRecording ? <View style={[styles.row, {padding: 10}]}><Text style={{color: colors.danger}}>●</Text><Text style={styles.text}>{t('recording')} {Math.floor(voice.recording.durationMillis / 1000)}s</Text><View style={{flex: 1}}/><IconButton name="close" label={t('cancel')} onPress={() => void voice.cancel().catch(e => setError(e.message))}/></View> : voice.busy ? <Text style={[styles.muted, {padding: 12}]}>{t('transcribing')}</Text> :
        <TextInput accessibilityLabel={t('placeholder')} style={styles.draft} placeholder={t('placeholder')} placeholderTextColor={colors.muted} value={draft.text} editable={!pendingSend && !sending} multiline onChangeText={text => { updateDraft({text}); if (text === '/') { setPanel('skills'); setSearch(''); } }}/>}
      <View style={styles.row}><IconButton name="add" label={t('add')} disabled={uploading || !!pendingSend} onPress={() => setPanel('add')}/><View style={{flex: 1}}/>
        <Pressable accessibilityRole="button" onPress={() => setPanel('model')} style={{minHeight: 44, justifyContent: 'center', maxWidth: '48%', flexShrink: 1, paddingHorizontal: 8}}><Text numberOfLines={1} style={styles.muted}>{providers.find(p => p.name === provider)?.display_name || t('model')} ⌄</Text></Pressable>
        <IconButton name={voice.recording.isRecording ? 'stop' : 'mic-outline'} label={voice.recording.isRecording ? t('finish') : t('record')} disabled={voice.busy || !!pendingSend} onPress={() => { if (!voice.recording.isRecording) recordSession.current = sessionId; void voice.toggle(); }}/>
        {active ? <IconButton name="stop" label={t('stop')} primary onPress={() => { void client.post('/api/chat/stop', {session_id: sessionId, run_id: active.id}).catch(e => setError(e.message)); }}/> :
          <IconButton name="arrow-up" label={pendingSend ? t('retry') : t('send')} primary disabled={sending || uploading || voice.busy || voice.recording.isRecording || !provider || (!draft.text.trim() && !pendingSend)} onPress={() => void send()}/>}
      </View>
    </View>
    {panel && <Sheet title={t(panel === 'model' ? 'model' : panel === 'sessions' ? 'sessions' : panel === 'settings' ? 'settings' : panel === 'skills' ? 'skills' : 'add')} closeLabel={t('close')} onClose={() => setPanel(null)}>
      {panel === 'sessions' && <><Button title={`+ ${t('task')}`} onPress={() => selectSession(id())}/>{rows(sessions.map(s => ({key: s.id, title: s.title, subtitle: Object.values(runs).some(r => r.session_id === s.id && isActive(r)) ? t('working') : s.updated_at.slice(0, 16).replace('T', ' '), action: () => selectSession(s.id)})))}{!sessions.length && <Text style={styles.muted}>{t('empty')}</Text>}</>}
      {panel === 'settings' && <><Text style={styles.label}>{client.credentials.identity.username}</Text><Text selectable style={styles.muted}>{client.credentials.origin}</Text>{rows(languages.map(l => ({key: l, title: languageNames[l] + (language === l ? ' ✓' : ''), action: () => void changeLanguage(l)})))}<Button title={t('logout')} onPress={() => void logout()}/></>}
      {panel === 'model' && <>{rows(providers.filter(p => p.configured).map(p => ({key: p.name, title: p.display_name, subtitle: p.model, action: () => {setProvider(p.name); setPanel(null);}})))}{!providers.some(p => p.configured) && <Text style={styles.muted}>{t('noModel')}</Text>}</>}
      {panel === 'add' && rows([{key: 'skills', title: t('skills'), action: () => {setSearch(''); setPanel('skills');}}, {key: 'files', title: t('files'), action: () => void upload()}])}
      {panel === 'skills' && <><TextInput accessibilityLabel={t('search')} placeholder={t('search')} style={styles.input} value={search} onChangeText={setSearch}/>{rows(skills.filter(s => `${s.name} ${s.display_name} ${s.description} ${s.display_description}`.toLowerCase().includes(search.toLowerCase())).map(s => ({key: s.name, title: s.display_name || s.name, subtitle: s.display_description || s.description, action: () => {updateDraft({skill: s, text: draft.text === '/' ? '' : draft.text}); setPanel(null);}})))}</>}
    </Sheet>}
  </KeyboardAvoidingView>;
}
const markdownStyles = {body: {color: colors.ink, fontSize: 16, lineHeight: 25}, paragraph: {marginTop: 6, marginBottom: 6}, heading1: {fontSize: 23}, heading2: {fontSize: 20}, heading3: {fontSize: 17}, table: {borderColor: colors.border, borderWidth: 1}, th: {padding: 6, backgroundColor: colors.surface}, td: {padding: 6}, link: {color: colors.blue}};

const MarkdownContent = React.memo(function MarkdownContent({text}: {text: string}) {
  return <Markdown style={markdownStyles} onLinkPress={url => { if (/^https?:\/\//i.test(url)) void Linking.openURL(url); return false; }}
    rules={{image: () => null, table: (node, children) => <ScrollView key={node.key} horizontal><View style={{minWidth: 580, borderWidth: 1, borderColor: colors.border}}>{children}</View></ScrollView>}}>{text}</Markdown>;
});
