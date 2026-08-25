import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

export function AboutPage() {
  return (
    <div className="page-shell static-page">
      <section className="static-intro"><div><p className="eyebrow">About the portal</p><h1>A clearer route through supplier stock.</h1><p>Straiit Stock Portal consolidates product offers imported from supplier spreadsheets and catalogues into one searchable interface. The portal keeps the source data intact while making product identity, imagery, stock, pricing and specifications easier to compare.</p><p>Availability and commercial fields vary by supplier. Missing data is identified explicitly rather than inferred, and the trading desk can confirm current terms against a product reference.</p></div><div className="principles"><Principle index="01" title="Source traceability" body="Each product remains linked internally to its imported source file and location." /><Principle index="02" title="No invented stock" body="Missing quantities and product attributes are presented as unavailable, never converted to misleading zero values." /><Principle index="03" title="Native pricing" body="Wholesale and retail prices remain in the currency supplied by the source catalogue." /><Principle index="04" title="Heterogeneous detail" body="Category-specific fields are shown only when the supplier data contains them." /></div></section>
      <div className="button-row"><Link className="button button-primary" to="/stock">Browse stock <ArrowRight aria-hidden="true" /></Link><Link className="button button-secondary" to="/support">Contact the desk</Link></div>
    </div>
  )
}

function Principle({ index, title, body }: { index: string; title: string; body: string }) {
  return <article><span>{index}</span><h2>{title}</h2><p>{body}</p></article>
}
