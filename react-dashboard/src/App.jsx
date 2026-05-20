import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Inbox from './components/widgets/Inbox'
import Processing from './components/widgets/Processing'
import Outbox from './components/widgets/Outbox'
import Stats from './components/widgets/Stats'
import Settings from './components/widgets/Settings'

export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
      <Dashboard>
        <div className="col-span-3 flex flex-col gap-4 overflow-hidden">
          <Inbox />
          <Processing />
          <Outbox />
        </div>
        <div className="col-span-2 flex flex-col gap-4 overflow-hidden">
          <Stats />
          <Settings />
        </div>
      </Dashboard>
    </div>
  )
}
