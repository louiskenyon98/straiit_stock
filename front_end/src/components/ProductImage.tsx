import { ImageIcon } from 'lucide-react'

interface ProductImageProps {
  src: string | null
  alt: string
  className?: string
}

export function ProductImage({ src, alt, className = '' }: ProductImageProps) {
  return (
    <div className={`product-image duotone ${className}`.trim()}>
      {src ? <img src={src} alt={alt} loading="lazy" /> : (
        <div className="image-placeholder" role="img" aria-label="No product image available">
          <ImageIcon aria-hidden="true" />
          <span>Image not supplied</span>
        </div>
      )}
    </div>
  )
}
