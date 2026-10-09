import React, { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useAuth } from '../hooks/useAuth.jsx';
import { Button, Card, Field, InlineError } from '../components/ui.jsx';

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  return (
    <div className="login-wrap">
      <Card className="login" title="IntentGuard Recovery" icon={<ShieldCheck size={18} color="var(--accent-cyan)" />}>
        <form className="stack" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await login(email.trim(), password);
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}>
          <p className="muted small" style={{ margin: 0 }}>
            Research prototype against a simulated payment provider. No real money.
          </p>
          <Field label="Email"><input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Password"><input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <InlineError error={error} />
          <Button className="btn-primary" busy={busy} type="submit">Sign in</Button>
          <p className="tiny muted" style={{ margin: 0 }}>
            Demo users (DEMO_SEED): asha@intentguard.test (operator), meera@intentguard.test (reviewer),
            admin@intentguard.test (admin). Password: DEMO_PASSWORD, default <span className="mono">intentguard-demo</span>.
          </p>
        </form>
      </Card>
    </div>
  );
}
