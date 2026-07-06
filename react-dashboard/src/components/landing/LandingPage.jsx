import Hero from './Hero'
import HowItWorks from './HowItWorks'
import Features from './Features'
import SignInCard from './SignInCard'

export default function LandingPage({ me, betaClosed }) {
  const isAuthed = !!me

  const handleCta = () => {
    if (isAuthed) {
      window.location.href = '/'
    } else {
      document.getElementById('signin')?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="min-h-screen bg-space-bg text-space-text">
      <Hero isAuthed={isAuthed} onCtaClick={handleCta} />
      <HowItWorks />
      <Features />
      <div className="px-6 pb-28 pt-8">
        <SignInCard isAuthed={isAuthed} betaClosed={betaClosed} />
      </div>
    </div>
  )
}
