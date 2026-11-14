import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { languages, type Language } from "../i18n";
const labels: Record<Language, string> = { "zh-CN": "简体中文", "zh-TW": "繁體中文", en: "English" };
export function LanguagePicker() {
  const { t, i18n } = useTranslation();
  const [pointerFocus, setPointerFocus] = useState(false);
  return <label className="model-picker language-picker">
    <select aria-label={t("界面语言")} data-pointer-focus={pointerFocus || undefined} onPointerDown={() => setPointerFocus(true)} onKeyDown={() => setPointerFocus(false)} onBlur={() => setPointerFocus(false)} name="ui-language" value={i18n.resolvedLanguage} onChange={event => void i18n.changeLanguage(event.target.value)}>
      {languages.map(language => <option key={language} value={language} lang={language}>{labels[language]}</option>)}
    </select><ChevronDown size={15} aria-hidden="true" />
  </label>;
}
