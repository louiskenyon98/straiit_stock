import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

interface BlueprintProps<T extends ElementType> {
  as?: T
  children: ReactNode
  className?: string
}

export function Blueprint<T extends ElementType = 'div'>({
  as,
  children,
  className = '',
  ...props
}: BlueprintProps<T> & Omit<ComponentPropsWithoutRef<T>, keyof BlueprintProps<T>>) {
  const Component = as ?? 'div'
  return (
    <Component className={`blueprint ${className}`.trim()} {...props}>
      {children}
      <i aria-hidden="true" className="corner corner-tl" />
      <i aria-hidden="true" className="corner corner-tr" />
      <i aria-hidden="true" className="corner corner-bl" />
      <i aria-hidden="true" className="corner corner-br" />
    </Component>
  )
}
