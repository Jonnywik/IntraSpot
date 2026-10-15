export type EventListing = {
  id: string;
  organization: string;
  category: string;
  title: string;
  summary: string;
  description: string;
  startsAt: string;
  location: string;
  confirmedAttendees: number;
  capacity: number;
  artClass: string;
  artWord: string;
};

export const events: EventListing[] = [
  {
    id: "campus-design-jam",
    organization: "Creative Society",
    category: "MAKE",
    title: "Campus Design Jam",
    summary: "An afternoon to sketch, share ideas, and make something together.",
    description:
      "Bring a half-formed idea or start with a blank page. We’ll work in small teams, try a few fast creative prompts, and share what we make before the afternoon ends. All experience levels are welcome.",
    startsAt: "2026-10-10T14:00:00+08:00",
    location: "Innovation Lab, North Campus",
    confirmedAttendees: 34,
    capacity: 50,
    artClass: "event-art--coral",
    artWord: "MAKE",
  },
  {
    id: "night-market-social",
    organization: "Student Activities Council",
    category: "GATHER",
    title: "Night Market Social",
    summary: "Local food, small makers, and a good reason to stay on campus.",
    description:
      "Meet student makers and neighborhood food stalls at the campus quad. Wander at your own pace, bring friends, and discover a few new favorites. Entry is free; food and handmade goods are available for purchase.",
    startsAt: "2026-10-13T17:30:00+08:00",
    location: "Central Quad",
    confirmedAttendees: 82,
    capacity: 120,
    artClass: "event-art--lavender",
    artWord: "GATHER",
  },
  {
    id: "campus-garden-day",
    organization: "Green Steps Collective",
    category: "GIVE BACK",
    title: "Campus Garden Day",
    summary: "Help turn a quiet corner of campus into a greener shared space.",
    description:
      "Spend a relaxed morning planting herbs and native flowers with the Green Steps team. Tools and gloves are provided. Wear comfortable clothes, bring a water bottle, and stay for as long as you can.",
    startsAt: "2026-10-17T09:00:00+08:00",
    location: "Garden Courtyard, East Wing",
    confirmedAttendees: 19,
    capacity: 30,
    artClass: "event-art--green",
    artWord: "GROW",
  },
  {
    id: "open-mic-after-class",
    organization: "The Listening Room",
    category: "PERFORM",
    title: "Open Mic After Class",
    summary: "Songs, stories, and small surprises from people around campus.",
    description:
      "Settle in for an easygoing evening of student performances. The list is open to singers, poets, storytellers, and first-timers. Come to perform or just enjoy the room and cheer people on.",
    startsAt: "2026-10-21T18:00:00+08:00",
    location: "The Commons, Room 204",
    confirmedAttendees: 26,
    capacity: 45,
    artClass: "event-art--blue",
    artWord: "SOUND",
  },
];

export function getSpotsLeft(event: EventListing) {
  return Math.max(0, event.capacity - event.confirmedAttendees);
}

export function formatEventDate(startsAt: string) {
  return new Intl.DateTimeFormat("en-PH", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "Asia/Manila",
  }).format(new Date(startsAt));
}

export function formatEventTime(startsAt: string) {
  return new Intl.DateTimeFormat("en-PH", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Manila",
  }).format(new Date(startsAt));
}

export function formatEventDay(startsAt: string) {
  return new Intl.DateTimeFormat("en-PH", {
    day: "2-digit",
    timeZone: "Asia/Manila",
  }).format(new Date(startsAt));
}

export function formatEventMonth(startsAt: string) {
  return new Intl.DateTimeFormat("en-PH", {
    month: "short",
    timeZone: "Asia/Manila",
  })
    .format(new Date(startsAt))
    .toUpperCase();
}
