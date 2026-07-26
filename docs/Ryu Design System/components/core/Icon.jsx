import React from 'react';

/* Ícones monocromáticos (stroke, sem cor própria — herdam currentColor), via Lucide CDN.
   Substituição intencional: o repositório do Ryu não define nenhuma biblioteca de ícones. */
export function Icon({ name, size = 18, strokeWidth = 1.75, style, ...rest }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const host = ref.current;
    if (!host) return;
    host.innerHTML = '';
    const el = document.createElement('i');
    el.setAttribute('data-lucide', name);
    el.setAttribute('width', size);
    el.setAttribute('height', size);
    el.setAttribute('stroke-width', strokeWidth);
    host.appendChild(el);
    if (window.lucide) window.lucide.createIcons({ nodes: [el] });
  }, [name, size, strokeWidth]);
  return <span ref={ref} style={{ display: 'inline-flex', width: size, height: size, color: 'currentColor', flexShrink: 0, ...style }} {...rest} />;
}
