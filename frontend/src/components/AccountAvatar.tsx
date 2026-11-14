// A small original illustrated character, separate from the assistant portrait.
export function AccountAvatar() {
  return <svg className="account-character" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
    <circle cx="20" cy="20" r="20" fill="#FFE6A0" />
    <path d="M2 21C2 9 10 4 20 6c11 1 16 10 13 20-3 9-12 13-21 8C5 31 2 27 2 21Z" fill="#FF647D" />
    <path d="M10 11c2-5 8-6 12-3-3 0-5 2-6 5-2-1-4-2-6-2Z" fill="#FF8B9B" />
    <ellipse cx="15" cy="20" rx="2" ry="3" fill="#452C44" transform="rotate(-13 15 20)" />
    <ellipse cx="26" cy="18" rx="2" ry="3" fill="#452C44" transform="rotate(-13 26 18)" />
    <circle cx="15.6" cy="19" r=".7" fill="white" /><circle cx="26.6" cy="17" r=".7" fill="white" />
    <path d="M19 25q3 3 5-1" fill="none" stroke="#6D304B" strokeWidth="1.7" strokeLinecap="round" />
    <ellipse cx="10" cy="25" rx="3" ry="1.6" fill="#FFABAE" /><ellipse cx="30" cy="22" rx="2.5" ry="1.5" fill="#FFABAE" />
  </svg>;
}
