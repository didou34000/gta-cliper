export const metadata = { title: "Connexion · GTA Clipper" };

export default async function Login({ searchParams }: { searchParams: Promise<{ e?: string }> }) {
  const { e } = await searchParams;
  return (
    <main className="login">
      <form method="post" action="/api/login" className="login-box">
        <div className="logo">
          <span className="logo-mark">VI</span>
          <span className="logo-txt"><b>GTA Clipper</b><small>@gta6francenews</small></span>
        </div>
        <label htmlFor="password">Mot de passe</label>
        <input id="password" name="password" type="password" inputMode="numeric" autoComplete="current-password" autoFocus required />
        {e && <p className="err">Mot de passe incorrect.</p>}
        <button type="submit" className="btn-primary">Entrer</button>
      </form>
    </main>
  );
}
