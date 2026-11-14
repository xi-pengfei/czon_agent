import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { translations, storage, documentStub } from './i18n-helper.mjs';
const { default: i18n, t, savedLanguage } = translations;
const catalogs = ['zh-CN', 'zh-TW', 'en'].map(code => JSON.parse(readFileSync(new URL(`../src/locales/${code}.json`, import.meta.url))));
test('all language catalogs contain the same keys and interpolation variables', () => {
  const keys = Object.keys(catalogs[0]).sort();
  for (const catalog of catalogs) {
    assert.deepEqual(Object.keys(catalog).sort(), keys);
    for (const key of keys) {
      assert.ok(catalog[key].trim());
      assert.deepEqual((catalog[key].match(/{{\w+}}/g) || []).sort(), (catalogs[0][key].match(/{{\w+}}/g) || []).sort(), key);
    }
  }
});
test('switching translates UI, persists preference and updates document language', async () => {
  assert.equal(savedLanguage(), 'zh-CN');
  await i18n.changeLanguage('en');
  assert.equal(t('新任务'), 'New task');
  assert.equal(t('重置 {{value0}} 的密码', { value0: '张三 <b> & 王' }), 'Reset password for 张三 <b> & 王');
  assert.equal(documentStub.documentElement.lang, 'en');
  assert.equal(savedLanguage(), 'en');
  await i18n.changeLanguage('zh-TW');
  assert.equal(t('选择技能'), '選擇技能');
  assert.equal(t('用户名或密码错误'), '使用者名稱或密碼錯誤');
  storage.set('czon.ui.language', 'invalid');
  assert.equal(savedLanguage(), 'zh-CN');
  await i18n.changeLanguage('zh-CN');
  assert.equal(t('新任务'), '新任务');
});
test('names, skill content and chat text stay outside the translation boundary', () => {
  const read = path => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8');
  assert.ok(read('components/Composer.tsx').includes('{item.display_name || item.name}'));
  assert.ok(read('components/Composer.tsx').includes('{item.display_description || item.description}'));
  assert.ok(read('components/MessageList.tsx').includes('{message.content}'));
  assert.ok(read('pages/ChatPage.tsx').includes('userName={identity.username}'));
  assert.ok(!read('hooks/useRuns.ts').includes('from "../i18n"'));
});
