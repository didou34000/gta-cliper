export const metadata = { title: "Connexion · GTA Clipper" };

export default async function Login({ searchParams }: { searchParams: Promise<{ e?: string }> }) {
  const { e } = await searchParams;
  return (
    <main className="login">
      <form method="post" action="/api/login" className="login-box">
        <h1>GTA Clipper</h1>
        <label htmlFor="password">Mot de passe</label>
        <input id="password" name="password" type="password" autoFocus required />
        {e && <p className="err">Mot de passe incorrect.</p>}
        <button type="submit">Entrer</button>
      </form>
    </main>
  );
}
