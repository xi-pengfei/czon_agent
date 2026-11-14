import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zhCN from "./locales/zh-CN.json";
import zhTW from "./locales/zh-TW.json";
import en from "./locales/en.json";

export const languages = ["zh-CN", "zh-TW", "en"] as const;
export type Language = typeof languages[number];
const storageKey = "czon.ui.language";
export function savedLanguage(): Language {
  try {
    const value = localStorage.getItem(storageKey);
    if (languages.includes(value as Language)) return value as Language;
  } catch { /* Private browsing may disable storage. */ }
  return "zh-CN";
}
void i18n.use(initReactI18next).init({
  resources: { "zh-CN": { translation: zhCN }, "zh-TW": { translation: zhTW }, en: { translation: en } },
  lng: savedLanguage(), fallbackLng: "zh-CN", supportedLngs: [...languages],
  keySeparator: false, nsSeparator: false,
  interpolation: { escapeValue: false },
});
function updateLanguage(language: string) {
  document.documentElement.lang = language;
  try { localStorage.setItem(storageKey, language); } catch { /* Keep in-memory selection. */ }
}
i18n.on("languageChanged", updateLanguage);
updateLanguage(i18n.language);
// Use at the presentation boundary only; never translate identifiers or user content.
export const t = (key: string, values?: Record<string, unknown>): string => i18n.t(key, values || {});
export default i18n;
