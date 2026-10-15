export function Icon({name}: {name: 'home'|'calendar'|'chat'|'settings'|'bell'|'filter'}) {
  const paths = {
    home: <path d="m3 10 9-7 9 7v11h-6v-8H9v8H3z"/>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/></>,
    chat: <path d="M21 11a9 9 0 0 1-9 9H4l-2 2V11a9 9 0 0 1 19 0Z"/>,
    settings: <><circle cx="12" cy="12" r="4"/><path d="m9 3 1 3h4l1-3 3 2-1 3 2 3 3 1-1 4-3 1-2 3-4-1-3 1-2-3-3-1 1-4 2-3-1-3Z"/></>,
    bell: <path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 21h4"/>,
    filter: <><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2" fill="white"/><circle cx="16" cy="12" r="2" fill="white"/><circle cx="10" cy="18" r="2" fill="white"/></>,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
