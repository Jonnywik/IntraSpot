export interface GuardAuthSession {
  access_token?: string | null;
  user?: { id?: string | null } | null;
}

export interface VerificationTicket {
  generation: number;
  userId: string;
  accessToken: string;
}

export function createRealSessionGuard() {
  let generation = 0;
  let userId: string | null = null;
  let accessToken: string | null = null;
  let logoutFenced = false;

  return {
    get generation() {
      return generation;
    },
    get userId() {
      return userId;
    },
    get accessToken() {
      return accessToken;
    },
    get isLogoutFenced() {
      return logoutFenced;
    },
    receive(event: string, session: GuardAuthSession | null) {
      const nextToken = session?.access_token;
      const nextUserId = session?.user?.id;
      const hasValidSession = Boolean(nextToken && nextUserId);

      if (hasValidSession && logoutFenced) {
        return {
          accepted: false,
          generation,
          userId,
          accessToken,
          hadAccount: false,
          changedAccount: false,
        };
      }

      const hadAccount = userId !== null;
      generation += 1;
      if (!hasValidSession) {
        userId = null;
        accessToken = null;
        if (event === 'SIGNED_OUT' || hadAccount) logoutFenced = true;
        return {
          accepted: true,
          generation,
          userId,
          accessToken,
          hadAccount,
          changedAccount: hadAccount,
        };
      }

      const changedAccount = userId !== nextUserId;
      userId = nextUserId!;
      accessToken = nextToken!;
      return {
        accepted: true,
        generation,
        userId,
        accessToken,
        hadAccount,
        changedAccount,
      };
    },
    beginLogout() {
      const hadAccount = userId !== null;
      generation += 1;
      logoutFenced = true;
      userId = null;
      accessToken = null;
      return { generation, hadAccount };
    },
    captureVerification(): VerificationTicket | null {
      if (logoutFenced || !userId || !accessToken) return null;
      generation += 1;
      return { generation, userId, accessToken };
    },
    isCurrent(ticket: VerificationTicket): boolean {
      return !logoutFenced &&
        generation === ticket.generation &&
        userId === ticket.userId &&
        accessToken === ticket.accessToken;
    },
    invalidate() {
      generation += 1;
    },
  };
}
