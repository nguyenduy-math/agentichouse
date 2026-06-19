import AppShell from './components/layout/AppShell'
import { useSession } from './hooks/useSession'

export default function App() {
  useSession()
  return <AppShell />
}
