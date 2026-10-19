# Sprint 15 interaction handoff — isolated development auth

In progress; actual user-controlled Google sign-in is an external acceptance
dependency. This is not a new public-release design or a Penpot synchronization.

- The existing four attendee destinations and desktop-only management remain.
  Shared private-page prompts refer to sign-in in the header rather than
  instructing real-development users to choose a fictional account.
- The normal 3000 build keeps its explicitly fictional selector. Only the
  separately configured 3001 build offers Google sign-in. The isolated label and
  footer must remain visible and must never imply production readiness.
- Explanations cover personal-account eligibility, incomplete private profiles,
  no automatic administrative/membership grants and memory-only sessions.
  The header must keep the primary control compact; longer explanations belong
  in an accessible disclosure rather than replacing the approved navigation.
- Google consent occurs on the provider's page, controlled by the user. The
  local callback is fixed to the same origin, removes response codes/errors from
  its URL before exchange, and never renders raw provider error descriptions.
- Account verification, callback failure, unavailable API/provider and retry are
  distinct from an accepted application session. A personal Google account can
  browse, but PLM-only actions are still enforced by the local API.
- Session credentials are memory-only. Reloading requires a new sign-in;
  same-tab session storage contains only expiring PKCE verifier material until
  consumed/cancelled. No real email appears in the header. Sign-out must hide
  private UI immediately and reject stale completion/refresh events.
- All new visible strings use the existing English/Filipino translation system.
  Do not add a fifth mobile destination or mobile organization-management UI.

Browser protocol tests with synthetic identities validate integration behavior,
not participant usability or actual OAuth. Actual Google, live PLM verification,
participant/native-device testing and security/release approval remain separate
gates. No participant results or screenshots of actual account data should be
invented from synthetic test evidence.
