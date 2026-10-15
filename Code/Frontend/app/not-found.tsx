import Link from "next/link";

export default function NotFound() {
  return (
    <section className="panel not-found">
      <p className="eyebrow"><span>404</span> WRONG TURN</p>
      <h1>This event wandered off<span className="heading-period">.</span></h1>
      <p>It may have moved or no longer be available.</p>
      <Link className="button button-secondary" href="/">Back to events <span aria-hidden="true">↗</span></Link>
    </section>
  );
}
