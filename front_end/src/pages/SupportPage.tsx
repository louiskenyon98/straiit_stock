import { Mail, Phone } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { Blueprint } from '../components/Blueprint'

export function SupportPage() {
  const [params] = useSearchParams()
  const reference = [params.get('product') && `Product ${params.get('product')}`, params.get('sku') && `SKU ${params.get('sku')}`].filter(Boolean).join(' · ')
  const subject = encodeURIComponent(reference ? `Stock enquiry — ${reference}` : 'Stock portal enquiry')
  return (
    <div className="page-shell support-page">
      <section className="support-grid">
        <div><p className="eyebrow">Support</p><h1>Talk to the trading desk.</h1><p className="hero-lede">For availability, volume pricing or product documentation, include the product ID or SKU from the catalogue.</p><dl className="contact-list"><div><dt>Sales and catalogue enquiries</dt><dd><a href={`mailto:sales@straiit.trade?subject=${subject}`}><Mail aria-hidden="true" /> sales@straiit.trade</a></dd></div><div><dt>Telephone</dt><dd><a href="tel:+31105550148"><Phone aria-hidden="true" /> +31 10 555 0148</a></dd></div><div><dt>Desk hours</dt><dd>Monday–Friday, 08:00–18:00 CET</dd></div></dl></div>
        <Blueprint className="contact-panel"><p className="eyebrow">Email enquiry</p><h2>{reference ? 'Product reference ready' : 'Start an enquiry'}</h2>{reference && <p className="reference-plate">{reference}</p>}<p>This first catalogue release does not simulate form submission. Use the email link below so your enquiry reaches the trading desk directly.</p><a className="button button-primary button-wide" href={`mailto:sales@straiit.trade?subject=${subject}`}><Mail aria-hidden="true" /> Compose email</a></Blueprint>
      </section>
    </div>
  )
}
