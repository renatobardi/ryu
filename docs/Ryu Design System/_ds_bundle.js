/* @ds-bundle: {"format":4,"namespace":"RyuDesignSystem_7ed69e","components":[{"name":"AgentCard","sourcePath":"components/app/AgentCard.jsx"},{"name":"BoardColumn","sourcePath":"components/app/BoardColumn.jsx"},{"name":"ChatBubble","sourcePath":"components/app/ChatBubble.jsx"},{"name":"InboxItem","sourcePath":"components/app/InboxItem.jsx"},{"name":"IssueCard","sourcePath":"components/app/IssueCard.jsx"},{"name":"NavItem","sourcePath":"components/app/NavItem.jsx"},{"name":"Sidebar","sourcePath":"components/app/Sidebar.jsx"},{"name":"SidebarSection","sourcePath":"components/app/Sidebar.jsx"},{"name":"StatCard","sourcePath":"components/app/StatCard.jsx"},{"name":"TopBar","sourcePath":"components/app/TopBar.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"EmptyState","sourcePath":"components/core/EmptyState.jsx"},{"name":"Icon","sourcePath":"components/core/Icon.jsx"},{"name":"Input","sourcePath":"components/core/Input.jsx"},{"name":"Select","sourcePath":"components/core/Select.jsx"},{"name":"Textarea","sourcePath":"components/core/Textarea.jsx"},{"name":"ThemeToggle","sourcePath":"components/core/ThemeToggle.jsx"},{"name":"CountBadge","sourcePath":"components/data/CountBadge.jsx"},{"name":"DataTable","sourcePath":"components/data/DataTable.jsx"},{"name":"IssueKey","sourcePath":"components/data/IssueKey.jsx"},{"name":"PriorityTag","sourcePath":"components/data/PriorityTag.jsx"},{"name":"StatusDot","sourcePath":"components/data/StatusDot.jsx"},{"name":"StatusPill","sourcePath":"components/data/StatusPill.jsx"}],"sourceHashes":{"components/app/AgentCard.jsx":"6531babf7bfc","components/app/BoardColumn.jsx":"dec7a8461307","components/app/ChatBubble.jsx":"011b1dd71683","components/app/InboxItem.jsx":"e119544c4200","components/app/IssueCard.jsx":"8504ce0294c8","components/app/NavItem.jsx":"76f4d528f1ee","components/app/Sidebar.jsx":"1bf719dd77d0","components/app/StatCard.jsx":"96d0564a7d83","components/app/TopBar.jsx":"aafeabb54941","components/core/Button.jsx":"1f3e41078d06","components/core/Card.jsx":"d132382db6b3","components/core/EmptyState.jsx":"bd02fa51ace5","components/core/Icon.jsx":"a592060df70b","components/core/Input.jsx":"09dd100a04fc","components/core/Select.jsx":"c8907da8962e","components/core/Textarea.jsx":"d729a71a0cda","components/core/ThemeToggle.jsx":"77c3f3d17dbd","components/data/CountBadge.jsx":"b4beb41e4f20","components/data/DataTable.jsx":"465ef71d32ba","components/data/IssueKey.jsx":"ab2be8fcb680","components/data/PriorityTag.jsx":"abe0296f4b8a","components/data/StatusDot.jsx":"b23e8fff3044","components/data/StatusPill.jsx":"e963634a10a1","ui_kits/ryu-app/App.jsx":"589dc020db98","ui_kits/ryu-app/Screens.jsx":"0740c9f311ed","ui_kits/ryu-app/Screens2.jsx":"0da1b5eeee87","ui_kits/ryu-app/Screens3.jsx":"d48fb7308b89","ui_kits/ryu-app/Screens4.jsx":"d5ac169c36e5","ui_kits/ryu-app/Shell.jsx":"866c807d8d0f","ui_kits/ryu-app/data.js":"525d1913d6d8"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.RyuDesignSystem_7ed69e = window.RyuDesignSystem_7ed69e || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/app/BoardColumn.jsx
try { (() => {
function BoardColumn({
  title,
  count = 0,
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: 'var(--board-column-width)',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface-column)',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid var(--border-default)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '8px 12px',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)',
      fontFamily: 'var(--font-sans)'
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, count)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      padding: 8,
      minHeight: 80,
      flex: 1
    }
  }, children));
}
Object.assign(__ds_scope, { BoardColumn });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/BoardColumn.jsx", error: String((e && e.message) || e) }); }

// components/app/ChatBubble.jsx
try { (() => {
function ChatBubble({
  role = 'agent',
  children,
  time,
  typing,
  style
}) {
  const user = role === 'user',
    system = role === 'system';
  const bg = user ? 'var(--accent)' : system ? 'var(--chat-bubble-system-bg)' : 'var(--chat-bubble-agent-bg)';
  const fg = user ? '#fff' : system ? 'var(--chat-bubble-system-fg)' : 'var(--chat-bubble-agent-fg)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: user ? 'flex-end' : 'flex-start',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: '75%',
      borderRadius: 'var(--radius-xl)',
      padding: '8px 12px',
      fontSize: 'var(--text-sm)',
      fontFamily: 'var(--font-sans)',
      whiteSpace: 'pre-wrap',
      background: bg,
      color: typing ? 'var(--text-subtle)' : fg,
      border: system ? '1px solid var(--border-default)' : undefined,
      animation: typing ? 'var(--animate-pulse)' : undefined
    }
  }, !user && !typing && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wide)',
      marginBottom: 4,
      color: system ? 'var(--chat-bubble-system-fg)' : 'var(--text-subtle)'
    }
  }, system ? 'sistema' : 'agente'), children, time && !typing && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      marginTop: 4,
      opacity: .6
    }
  }, time)));
}
Object.assign(__ds_scope, { ChatBubble });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/ChatBubble.jsx", error: String((e && e.message) || e) }); }

// components/app/InboxItem.jsx
try { (() => {
const SEV = {
  action_required: 'var(--red-500)',
  attention: 'var(--amber-400)',
  info: 'var(--zinc-500)'
};
const SEV_LABEL = {
  action_required: 'Ação necessária',
  attention: 'Atenção',
  info: 'Info'
};
function InboxItem({
  severity = 'info',
  title,
  body,
  time,
  read,
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 12,
      padding: '16px 24px',
      background: read ? 'transparent' : 'var(--surface-column)',
      borderBottom: '1px solid var(--border-default)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      marginTop: 4,
      width: 8,
      height: 8,
      borderRadius: 'var(--radius-full)',
      background: SEV[severity],
      flexShrink: 0
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontFamily: 'var(--font-sans)',
      color: read ? 'var(--text-muted)' : 'var(--text-primary)',
      fontWeight: read ? 'var(--weight-normal)' : 'var(--weight-medium)'
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wide)',
      color: 'var(--text-subtle)'
    }
  }, SEV_LABEL[severity])), body && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '2px 0 0',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, body), time && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '4px 0 0',
      fontSize: 'var(--text-11)',
      color: 'var(--text-faint)'
    }
  }, time)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 4
    }
  }, children));
}
Object.assign(__ds_scope, { InboxItem });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/InboxItem.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const VARIANTS = {
  primary: {
    background: 'var(--accent)',
    color: 'var(--text-on-accent)',
    border: '1px solid transparent'
  },
  secondary: {
    background: 'var(--zinc-800)',
    color: 'var(--text-body)',
    border: '1px solid transparent'
  },
  outline: {
    background: 'var(--surface-input)',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-strong)'
  },
  ghost: {
    background: 'transparent',
    color: 'var(--text-muted)',
    border: '1px solid transparent'
  },
  link: {
    background: 'transparent',
    color: 'var(--text-accent)',
    border: 'none',
    padding: 0
  },
  danger: {
    background: 'transparent',
    color: 'var(--text-subtle)',
    border: 'none',
    padding: 0
  }
};
const HOVER = {
  primary: 'var(--accent-hover)',
  secondary: 'var(--zinc-700)',
  outline: 'var(--zinc-800)',
  ghost: 'var(--surface-hover)',
  link: null,
  danger: null
};
const HOVER_FG = {
  ghost: 'var(--text-body)',
  link: 'var(--violet-300)',
  danger: 'var(--red-400)',
  outline: 'var(--text-body)'
};
const SIZES = {
  sm: {
    fontSize: 'var(--text-xs)',
    padding: '4px 12px'
  },
  md: {
    fontSize: 'var(--text-sm)',
    padding: '6px 16px'
  },
  lg: {
    fontSize: 'var(--text-sm)',
    padding: '8px 16px'
  }
};
function Button({
  variant = 'primary',
  size = 'md',
  disabled,
  full,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const v = VARIANTS[variant] || VARIANTS.primary;
  const bare = variant === 'link' || variant === 'danger';
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      font: 'var(--type-body)',
      fontWeight: 'var(--weight-medium)',
      borderRadius: 'var(--radius-md)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 'var(--space-1-5)',
      width: full ? '100%' : undefined,
      whiteSpace: 'nowrap',
      transition: 'background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out)',
      opacity: disabled ? 0.45 : 1,
      ...v,
      ...(bare ? {
        fontSize: 'var(--text-xs)'
      } : SIZES[size]),
      ...(hover && !disabled && HOVER[variant] ? {
        background: HOVER[variant]
      } : null),
      ...(hover && !disabled && HOVER_FG[variant] ? {
        color: HOVER_FG[variant]
      } : null),
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  panel: 'var(--surface-card)',
  raised: 'var(--surface-raised)',
  muted: 'var(--surface-column)',
  bare: 'transparent'
};
function Card({
  tone = 'panel',
  dashed,
  hoverable,
  pad = 16,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", _extends({
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      background: TONES[tone] || TONES.panel,
      border: '1px ' + (dashed ? 'dashed ' : 'solid ') + (hoverable && hover ? 'var(--border-hover)' : 'var(--border-default)'),
      borderRadius: 'var(--radius-lg)',
      padding: pad,
      boxSizing: 'border-box',
      boxShadow: tone === 'bare' ? undefined : 'var(--card-shadow)',
      transition: 'border-color var(--duration-fast) var(--ease-out)',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/EmptyState.jsx
try { (() => {
function EmptyState({
  children,
  dashed = true,
  pad = 24
}) {
  return /*#__PURE__*/React.createElement(__ds_scope.Card, {
    tone: "panel",
    dashed: dashed,
    pad: pad,
    style: {
      textAlign: 'center',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-subtle)'
    }
  }, children);
}
Object.assign(__ds_scope, { EmptyState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/EmptyState.jsx", error: String((e && e.message) || e) }); }

// components/core/Icon.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Ícones monocromáticos (stroke, sem cor própria — herdam currentColor), via Lucide CDN.
   Substituição intencional: o repositório do Ryu não define nenhuma biblioteca de ícones. */
function Icon({
  name,
  size = 18,
  strokeWidth = 1.75,
  style,
  ...rest
}) {
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
    if (window.lucide) window.lucide.createIcons({
      nodes: [el]
    });
  }, [name, size, strokeWidth]);
  return /*#__PURE__*/React.createElement("span", _extends({
    ref: ref,
    style: {
      display: 'inline-flex',
      width: size,
      height: size,
      color: 'currentColor',
      flexShrink: 0,
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { Icon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Icon.jsx", error: String((e && e.message) || e) }); }

// components/core/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Input({
  size = 'md',
  tone = 'raised',
  full = true,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const pad = size === 'sm' ? '6px 10px' : size === 'lg' ? '8px 12px' : '6px 12px';
  const fs = size === 'sm' ? 'var(--text-xs)' : 'var(--text-sm)';
  return /*#__PURE__*/React.createElement("input", _extends({
    onFocus: e => {
      setFocus(true);
      rest.onFocus && rest.onFocus(e);
    },
    onBlur: e => {
      setFocus(false);
      rest.onBlur && rest.onBlur(e);
    },
    style: {
      width: full ? '100%' : undefined,
      boxSizing: 'border-box',
      background: tone === 'sunken' ? 'var(--surface-input-alt)' : 'var(--surface-input)',
      border: '1px solid ' + (focus ? 'var(--border-focus)' : tone === 'sunken' ? 'var(--border-default)' : 'var(--border-strong)'),
      borderRadius: 'var(--radius-md)',
      padding: pad,
      fontSize: fs,
      fontFamily: 'var(--font-sans)',
      color: 'var(--text-primary)',
      outline: 'none',
      transition: 'border-color var(--duration-fast) var(--ease-out)',
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Input.jsx", error: String((e && e.message) || e) }); }

// components/app/Sidebar.jsx
try { (() => {
function Sidebar({
  user,
  onSearch,
  children,
  onProfileClick,
  style
}) {
  const initials = user ? (user.nickname || user.name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase() : '';
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 'var(--sidebar-width)',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      borderRight: '1px solid var(--border-soft)',
      background: 'var(--surface-chrome)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '18px 16px',
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 29,
      lineHeight: 1,
      color: 'var(--text-primary)',
      flexShrink: 0
    }
  }, "\u9F8D"), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 20,
      fontWeight: 800,
      letterSpacing: '-0.03em',
      color: 'var(--text-primary)',
      lineHeight: 1
    }
  }, "Ryu"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-subtle)'
    }
  }, "Agentic issue tracking"))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '12px 8px 0',
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Input, {
    size: "sm",
    placeholder: "Search  \u2318K",
    onChange: onSearch
  }), /*#__PURE__*/React.createElement(__ds_scope.Button, {
    full: true,
    size: "sm",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "plus",
    size: 14
  }), " New Issue")), /*#__PURE__*/React.createElement("nav", {
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: '12px 8px',
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, children), user && /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onProfileClick,
    style: {
      margin: 8,
      padding: '8px',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      background: 'transparent',
      border: 'none',
      borderRadius: 'var(--radius-md)',
      cursor: 'pointer',
      textAlign: 'left',
      transition: 'background var(--duration-fast) var(--ease-out)'
    },
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-hover)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent'
  }, user.avatar ? /*#__PURE__*/React.createElement("img", {
    src: user.avatar,
    alt: "",
    style: {
      width: 28,
      height: 28,
      borderRadius: 'var(--radius-full)',
      objectFit: 'cover',
      flexShrink: 0
    }
  }) : /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 'var(--radius-full)',
      background: 'var(--surface-active)',
      color: 'var(--text-secondary)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 'var(--text-2xs)',
      fontWeight: 'var(--weight-semibold)',
      flexShrink: 0
    }
  }, initials), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-secondary)',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, user.nickname || user.name)));
}
function SidebarSection({
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '12px 12px 4px',
      fontSize: 'var(--text-2xs)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wider)',
      color: 'var(--text-faint)'
    }
  }, children);
}
Object.assign(__ds_scope, { Sidebar, SidebarSection });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/Sidebar.jsx", error: String((e && e.message) || e) }); }

// components/core/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Select({
  size = 'md',
  tone = 'raised',
  full,
  children,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("select", _extends({
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      width: full ? '100%' : undefined,
      boxSizing: 'border-box',
      background: tone === 'sunken' ? 'var(--surface-input-alt)' : 'var(--surface-input)',
      border: '1px solid ' + (focus ? 'var(--border-focus)' : tone === 'sunken' ? 'var(--border-default)' : 'var(--border-strong)'),
      borderRadius: 'var(--radius-md)',
      padding: size === 'sm' ? '4px 8px' : '6px 8px',
      fontSize: size === 'sm' ? 'var(--text-xs)' : 'var(--text-sm)',
      fontFamily: 'var(--font-sans)',
      color: 'var(--text-secondary)',
      outline: 'none',
      cursor: 'pointer',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Select.jsx", error: String((e && e.message) || e) }); }

// components/core/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Textarea({
  tone = 'raised',
  mono,
  rows = 3,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("textarea", _extends({
    rows: rows,
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      width: '100%',
      boxSizing: 'border-box',
      resize: 'vertical',
      background: tone === 'sunken' ? 'var(--surface-input-alt)' : 'var(--surface-input)',
      border: '1px solid ' + (focus ? 'var(--border-focus)' : tone === 'sunken' ? 'var(--border-default)' : 'var(--border-strong)'),
      borderRadius: 'var(--radius-md)',
      padding: '8px 12px',
      fontSize: 'var(--text-sm)',
      fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)',
      color: 'var(--text-primary)',
      outline: 'none',
      lineHeight: 'var(--leading-normal)',
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Textarea.jsx", error: String((e && e.message) || e) }); }

// components/core/ThemeToggle.jsx
try { (() => {
function ThemeToggle({
  theme = 'light',
  onChange,
  style
}) {
  const isDark = theme === 'dark';
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => onChange && onChange(isDark ? 'light' : 'dark'),
    "aria-label": "Alternar tema",
    style: {
      width: 36,
      height: 36,
      borderRadius: 'var(--radius-md)',
      border: '1px solid var(--border-default)',
      background: 'var(--surface-input)',
      color: 'var(--text-muted)',
      cursor: 'pointer',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      transition: 'background var(--duration-fast) var(--ease-out)',
      ...style
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: isDark ? 'sun' : 'moon',
    size: 16
  }));
}
Object.assign(__ds_scope, { ThemeToggle });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/ThemeToggle.jsx", error: String((e && e.message) || e) }); }

// components/data/CountBadge.jsx
try { (() => {
function CountBadge({
  count = 0,
  tone = 'accent',
  hideZero = true,
  style
}) {
  if (hideZero && !count) return null;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-block',
      minWidth: 18,
      textAlign: 'center',
      fontSize: 'var(--text-2xs)',
      fontWeight: 'var(--weight-semibold)',
      fontFamily: 'var(--font-sans)',
      borderRadius: 'var(--radius-full)',
      padding: '2px 6px',
      background: tone === 'accent' ? 'var(--accent)' : 'var(--zinc-800)',
      color: tone === 'accent' ? 'var(--text-on-accent)' : 'var(--text-muted)',
      ...style
    }
  }, count);
}
Object.assign(__ds_scope, { CountBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/CountBadge.jsx", error: String((e && e.message) || e) }); }

// components/app/NavItem.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function NavItem({
  icon,
  label,
  active,
  count,
  href = '#',
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("a", _extends({
    href: href,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '6px 12px',
      borderRadius: 'var(--radius-md)',
      textDecoration: 'none',
      fontSize: 'var(--text-sm)',
      fontFamily: 'var(--font-sans)',
      background: active ? 'var(--surface-active)' : hover ? 'var(--surface-hover)' : 'transparent',
      color: active ? 'var(--text-primary)' : hover ? 'var(--text-body)' : 'var(--text-muted)',
      transition: 'background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 16,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      opacity: .85
    }
  }, icon), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1
    }
  }, label), count ? /*#__PURE__*/React.createElement(__ds_scope.CountBadge, {
    count: count
  }) : null);
}
Object.assign(__ds_scope, { NavItem });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/NavItem.jsx", error: String((e && e.message) || e) }); }

// components/app/TopBar.jsx
try { (() => {
function TopBar({
  connection = 'connected',
  inboxCount = 0,
  children,
  style
}) {
  const color = connection === 'connected' ? 'var(--emerald-500)' : connection === 'disconnected' ? 'var(--red-500)' : 'var(--text-faint)';
  return /*#__PURE__*/React.createElement("header", {
    style: {
      height: 'var(--topbar-height)',
      flexShrink: 0,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: 16,
      padding: '0 20px',
      borderBottom: '1px solid var(--border-soft)',
      background: 'var(--surface-chrome)',
      ...style
    }
  }, children, /*#__PURE__*/React.createElement("span", {
    title: "conex\xE3o realtime",
    style: {
      fontSize: 'var(--text-2xs)',
      color
    }
  }, "\u25CF"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      position: 'relative',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      textDecoration: 'none'
    }
  }, "Inbox", inboxCount > 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: -8,
      right: -16
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.CountBadge, {
    count: inboxCount
  }))));
}
Object.assign(__ds_scope, { TopBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/TopBar.jsx", error: String((e && e.message) || e) }); }

// components/data/DataTable.jsx
try { (() => {
function DataTable({
  columns = [],
  rows = [],
  empty = 'Sem dados.',
  bordered = true
}) {
  const table = /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      fontSize: 'var(--text-sm)',
      fontFamily: 'var(--font-sans)'
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      borderBottom: '1px solid var(--border-default)'
    }
  }, columns.map((c, i) => /*#__PURE__*/React.createElement("th", {
    key: i,
    style: {
      textAlign: c.align || 'left',
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-subtle)',
      padding: bordered ? '8px 16px' : '8px 16px 8px 0',
      whiteSpace: 'nowrap'
    }
  }, c.label)))), /*#__PURE__*/React.createElement("tbody", null, rows.length === 0 && /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: columns.length,
    style: {
      padding: '24px 16px',
      textAlign: 'center',
      color: 'var(--text-subtle)'
    }
  }, empty)), rows.map((r, i) => /*#__PURE__*/React.createElement("tr", {
    key: i,
    style: {
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, columns.map((c, j) => /*#__PURE__*/React.createElement("td", {
    key: j,
    style: {
      textAlign: c.align || 'left',
      padding: bordered ? '8px 16px' : '8px 16px 8px 0',
      color: c.muted ? 'var(--text-subtle)' : 'var(--text-secondary)',
      fontSize: c.small ? 'var(--text-xs)' : undefined,
      fontFamily: c.mono ? 'var(--font-mono)' : undefined,
      maxWidth: c.maxWidth,
      overflow: c.maxWidth ? 'hidden' : undefined,
      textOverflow: c.maxWidth ? 'ellipsis' : undefined,
      whiteSpace: c.maxWidth ? 'nowrap' : undefined
    }
  }, r[c.key]))))));
  if (!bordered) return table;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden'
    }
  }, table);
}
Object.assign(__ds_scope, { DataTable });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/DataTable.jsx", error: String((e && e.message) || e) }); }

// components/data/IssueKey.jsx
try { (() => {
function IssueKey({
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-key)',
      color: 'var(--text-subtle)',
      ...style
    }
  }, children);
}
Object.assign(__ds_scope, { IssueKey });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/IssueKey.jsx", error: String((e && e.message) || e) }); }

// components/data/PriorityTag.jsx
try { (() => {
const P = {
  urgent: ['--prio-urgent-bg', '--prio-urgent-fg'],
  high: ['--prio-high-bg', '--prio-high-fg'],
  medium: ['--prio-medium-bg', '--prio-medium-fg'],
  low: ['--prio-low-bg', '--prio-low-fg']
};
function PriorityTag({
  priority = 'medium',
  style
}) {
  if (priority === 'none') return null;
  const pair = P[priority] || P.low;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-pill)',
      textTransform: 'uppercase',
      borderRadius: 'var(--radius-sm)',
      padding: '2px 6px',
      background: 'var(' + pair[0] + ')',
      color: 'var(' + pair[1] + ')',
      ...style
    }
  }, priority);
}
Object.assign(__ds_scope, { PriorityTag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/PriorityTag.jsx", error: String((e && e.message) || e) }); }

// components/app/IssueCard.jsx
try { (() => {
function IssueCard({
  issueKey,
  title,
  priority = 'none',
  assignee,
  assigneeType = 'agent',
  onClick,
  style
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    draggable: true,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      background: 'var(--surface-raised)',
      border: '1px solid ' + (hover ? 'var(--border-hover)' : 'var(--border-default)'),
      borderRadius: 'var(--radius-md)',
      padding: 12,
      cursor: 'grab',
      transition: 'border-color var(--duration-fast) var(--ease-out)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.IssueKey, null, issueKey), /*#__PURE__*/React.createElement(__ds_scope.PriorityTag, {
    priority: priority
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      lineHeight: 'var(--leading-snug)',
      fontFamily: 'var(--font-sans)',
      color: hover ? 'var(--text-accent)' : 'var(--text-primary)'
    }
  }, title), assignee && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 'var(--text-2xs)',
      padding: '2px 6px',
      borderRadius: 'var(--radius-sm)',
      background: 'var(--surface-hover)',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: assigneeType === 'agent' ? 'bot' : 'user',
    size: 11
  }), assignee)));
}
Object.assign(__ds_scope, { IssueCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/IssueCard.jsx", error: String((e && e.message) || e) }); }

// components/data/StatusDot.jsx
try { (() => {
const COLORS = {
  backlog: 'var(--status-backlog)',
  todo: 'var(--status-todo)',
  in_progress: 'var(--status-in-progress)',
  in_review: 'var(--status-in-review)',
  done: 'var(--status-done)',
  blocked: 'var(--status-blocked)',
  cancelled: 'var(--status-cancelled)'
};
function StatusDot({
  status = 'backlog',
  size = 8,
  style
}) {
  return /*#__PURE__*/React.createElement("span", {
    "aria-label": status,
    style: {
      display: 'inline-block',
      width: size,
      height: size,
      borderRadius: 'var(--radius-full)',
      background: COLORS[status] || COLORS.backlog,
      flexShrink: 0,
      ...style
    }
  });
}
Object.assign(__ds_scope, { StatusDot });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/StatusDot.jsx", error: String((e && e.message) || e) }); }

// components/app/StatCard.jsx
try { (() => {
function StatCard({
  value,
  label,
  status,
  accent,
  hoverable,
  style
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      background: 'var(--surface-card)',
      border: '1px solid ' + (hoverable && hover ? 'var(--border-hover)' : 'var(--border-default)'),
      borderRadius: 'var(--radius-lg)',
      padding: 16,
      fontFamily: 'var(--font-sans)',
      transition: 'border-color var(--duration-fast) var(--ease-out)',
      ...style
    }
  }, label && !status && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      marginBottom: 4
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xl)',
      fontWeight: 'var(--weight-semibold)',
      color: accent ? 'var(--emerald-400)' : 'var(--text-primary)',
      lineHeight: 1.2
    }
  }, value), status && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 4,
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 'var(--text-xs)'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.StatusDot, {
    status: status
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, label)));
}
Object.assign(__ds_scope, { StatCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/StatCard.jsx", error: String((e && e.message) || e) }); }

// components/data/StatusPill.jsx
try { (() => {
const MAP = {
  agent: {
    idle: ['--agent-idle-bg', '--agent-idle-fg'],
    working: ['--agent-working-bg', '--agent-working-fg'],
    blocked: ['--agent-blocked-bg', '--agent-blocked-fg'],
    error: ['--agent-error-bg', '--agent-error-fg'],
    offline: ['--agent-offline-bg', '--agent-offline-fg']
  },
  task: {
    queued: ['--task-queued-bg', '--task-queued-fg'],
    dispatched: ['--task-dispatched-bg', '--task-dispatched-fg'],
    running: ['--task-running-bg', '--task-running-fg'],
    completed: ['--task-completed-bg', '--task-completed-fg'],
    failed: ['--task-failed-bg', '--task-failed-fg'],
    cancelled: ['--task-cancelled-bg', '--task-cancelled-fg']
  },
  severity: {
    action_required: ['--sev-action-required-bg', '--sev-action-required-fg'],
    attention: ['--sev-attention-bg', '--sev-attention-fg'],
    info: ['--sev-info-bg', '--sev-info-fg']
  },
  state: {
    on: ['--state-on-bg', '--state-on-fg'],
    off: ['--state-off-bg', '--state-off-fg']
  },
  neutral: {
    default: [null, null]
  }
};
function StatusPill({
  kind = 'task',
  status,
  children,
  style
}) {
  const pair = MAP[kind] && MAP[kind][status] || [null, null];
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-block',
      font: 'var(--type-pill)',
      borderRadius: 'var(--radius-full)',
      padding: 'var(--pill-pad-y) var(--pill-pad-x)',
      background: pair[0] ? 'var(' + pair[0] + ')' : 'var(--zinc-800)',
      color: pair[1] ? 'var(' + pair[1] + ')' : 'var(--text-muted)',
      whiteSpace: 'nowrap',
      ...style
    }
  }, children || status);
}
Object.assign(__ds_scope, { StatusPill });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/StatusPill.jsx", error: String((e && e.message) || e) }); }

// components/app/AgentCard.jsx
try { (() => {
function AgentCard({
  name,
  handle,
  runtime,
  status = 'idle',
  description,
  compact,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: compact ? 'var(--surface-card)' : 'var(--surface-column)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      padding: 16,
      display: 'flex',
      alignItems: compact ? 'center' : 'flex-start',
      gap: 12,
      fontFamily: 'var(--font-sans)',
      ...style
    }
  }, compact && /*#__PURE__*/React.createElement("div", {
    style: {
      width: 36,
      height: 36,
      borderRadius: 'var(--radius-lg)',
      background: 'var(--surface-hover)',
      color: 'var(--text-muted)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "bot",
    size: 18
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-primary)',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, name), compact && /*#__PURE__*/React.createElement(__ds_scope.StatusPill, {
    kind: "agent",
    status: status
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      marginTop: 2
    }
  }, "@", handle, " \xB7 ", runtime), description && !compact && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 4
    }
  }, description)), !compact && /*#__PURE__*/React.createElement(__ds_scope.StatusPill, {
    kind: "agent",
    status: status
  }));
}
Object.assign(__ds_scope, { AgentCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/AgentCard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/App.jsx
try { (() => {
function LoginScreen({
  onDone
}) {
  const {
    Card,
    Input,
    Button
  } = window.RyuDesignSystem_7ed69e;
  const [user, setUser] = React.useState('');
  const [password, setPassword] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 16,
      background: 'var(--surface-app)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: '100%',
      maxWidth: 384
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      marginBottom: 32,
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 44,
      lineHeight: 1,
      color: 'var(--text-primary)'
    }
  }, "\u9F8D"), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 28,
      fontWeight: 800,
      letterSpacing: '-0.03em',
      color: 'var(--text-primary)',
      lineHeight: 1
    }
  }, "Ryu"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      marginTop: 4
    }
  }, "Agentic issue tracking"))), /*#__PURE__*/React.createElement(Card, {
    tone: "panel",
    pad: 24,
    style: {
      borderRadius: 'var(--radius-xl)'
    }
  }, /*#__PURE__*/React.createElement("form", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    },
    onSubmit: e => {
      e.preventDefault();
      onDone();
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)'
    }
  }, "Usu\xE1rio"), /*#__PURE__*/React.createElement(Input, {
    required: true,
    placeholder: "voce@empresa.com",
    value: user,
    onChange: e => setUser(e.target.value),
    style: {
      padding: '8px 12px'
    }
  }), /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)'
    }
  }, "Senha"), /*#__PURE__*/React.createElement(Input, {
    type: "password",
    required: true,
    placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022",
    value: password,
    onChange: e => setPassword(e.target.value),
    style: {
      padding: '8px 12px'
    }
  }), /*#__PURE__*/React.createElement(Button, {
    type: "submit",
    full: true,
    size: "lg"
  }, "Entrar")))));
}
function App() {
  const D = window.RYU_DATA;
  const [authed, setAuthed] = React.useState(false);
  const [route, setRoute] = React.useState('dashboard');
  const [issues, setIssues] = React.useState(D.issues);
  const [inbox, setInbox] = React.useState(D.inbox);
  const [openIssue, setOpenIssue] = React.useState(null);
  const [openProject, setOpenProject] = React.useState(null);
  const [query, setQuery] = React.useState('');
  const [theme, setTheme] = React.useState('light');
  const [user, setUser] = React.useState({
    nickname: 'renatob',
    email: D.user.email
  });
  const unread = inbox.filter(i => !i.read).length;
  let seq = React.useRef(143);
  React.useEffect(() => {
    if (theme === 'dark') document.documentElement.setAttribute('data-theme', 'dark');else document.documentElement.removeAttribute('data-theme');
  }, [theme]);
  if (!authed) return /*#__PURE__*/React.createElement(LoginScreen, {
    onDone: () => setAuthed(true)
  });
  const addIssue = (title, status, assignee) => {
    setIssues(prev => [{
      key: D.workspace.prefix + '-' + seq.current++,
      title,
      status,
      priority: 'none',
      assignee: assignee || undefined
    }, ...prev]);
  };
  const patch = (key, field, value) => setIssues(prev => prev.map(i => i.key === key ? {
    ...i,
    [field]: value
  } : i));
  let screen;
  if (openIssue) {
    const live = issues.find(i => i.key === openIssue.key) || openIssue;
    screen = /*#__PURE__*/React.createElement(IssueScreen, {
      issue: live,
      back: () => setOpenIssue(null),
      patch: patch
    });
  } else if (openProject) {
    screen = /*#__PURE__*/React.createElement(ProjectDetailScreen, {
      project: openProject,
      issues: issues,
      back: () => setOpenProject(null)
    });
  } else if (route === 'dashboard') screen = /*#__PURE__*/React.createElement(DashboardScreen, {
    issues: issues,
    go: setRoute
  });else if (route === 'board') screen = /*#__PURE__*/React.createElement(BoardScreen, {
    issues: issues,
    addIssue: addIssue,
    openIssue: setOpenIssue
  });else if (route === 'chat') screen = /*#__PURE__*/React.createElement(ChatScreen, null);else if (route === 'inbox') screen = /*#__PURE__*/React.createElement(InboxScreen, {
    items: inbox,
    markAll: () => setInbox(p => p.map(i => ({
      ...i,
      read: true
    }))),
    markRead: n => setInbox(p => p.map((i, idx) => idx === n ? {
      ...i,
      read: true
    } : i))
  });else if (route === 'agents') screen = /*#__PURE__*/React.createElement(AgentsScreen, null);else if (route === 'usage') screen = /*#__PURE__*/React.createElement(UsageScreen, null);else if (route === 'profile') screen = /*#__PURE__*/React.createElement(ProfileScreen, {
    user: user,
    setUser: setUser,
    onLogout: () => setAuthed(false)
  });else if (route === 'projects') screen = /*#__PURE__*/React.createElement(ProjectsScreen, {
    open: setOpenProject
  });else if (route === 'runtimes') screen = /*#__PURE__*/React.createElement(RuntimesScreen, null);else if (route === 'settings') screen = /*#__PURE__*/React.createElement(SettingsScreen, {
    onLogout: () => setAuthed(false)
  });else if (route === 'my_issues') screen = /*#__PURE__*/React.createElement(MyIssuesScreen, {
    issues: issues,
    openIssue: setOpenIssue
  });else if (route === 'autopilots') screen = /*#__PURE__*/React.createElement(AutopilotsScreen, null);else if (route === 'skills') screen = /*#__PURE__*/React.createElement(SkillsScreen, null);else if (route === 'squads') screen = /*#__PURE__*/React.createElement(SquadsScreen, null);else if (route === 'members') screen = /*#__PURE__*/React.createElement(MembersScreen, null);else if (route === 'search') screen = /*#__PURE__*/React.createElement(SearchScreen, {
    query: query,
    setQuery: setQuery,
    issues: issues
  });else screen = /*#__PURE__*/React.createElement(StubScreen, {
    title: route.replace('_', ' '),
    note: "Tela existente no Ryu, n\xE3o recriada neste UI kit."
  });
  return /*#__PURE__*/React.createElement(Shell, {
    route: openIssue || openProject ? 'board' : route,
    unread: unread,
    theme: theme,
    setTheme: setTheme,
    user: user,
    query: query,
    setQuery: setQuery,
    setRoute: r => {
      setOpenIssue(null);
      setOpenProject(null);
      setRoute(r);
    }
  }, screen);
}
function mountApp() {
  if (window.__ryuMounted) return;
  if (!window.RyuDesignSystem_7ed69e || !window.Shell) {
    setTimeout(mountApp, 30);
    return;
  }
  window.__ryuMounted = true;
  ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountApp);else mountApp();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/App.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/Screens.jsx
try { (() => {
/* ── Board ─────────────────────────────────────────────────── */
function BoardScreen({
  issues,
  addIssue,
  openIssue
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    IssueCard,
    BoardColumn,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [title, setTitle] = React.useState('');
  const [status, setStatus] = React.useState('backlog');
  const [agent, setAgent] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: D.workspace.name,
    kicker: "Board",
    right: /*#__PURE__*/React.createElement("form", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 8
      },
      onSubmit: e => {
        e.preventDefault();
        if (!title.trim()) return;
        addIssue(title, status, agent);
        setTitle('');
      }
    }, /*#__PURE__*/React.createElement(Input, {
      full: false,
      style: {
        width: 256
      },
      placeholder: "Nova issue...",
      value: title,
      onChange: e => setTitle(e.target.value)
    }), /*#__PURE__*/React.createElement(Select, {
      value: status,
      onChange: e => setStatus(e.target.value)
    }, D.statusOrder.map(s => /*#__PURE__*/React.createElement("option", {
      key: s,
      value: s
    }, D.statusTitles[s]))), /*#__PURE__*/React.createElement(Select, {
      value: agent,
      onChange: e => setAgent(e.target.value)
    }, /*#__PURE__*/React.createElement("option", {
      value: ""
    }, "Sem agente"), D.agents.map(a => /*#__PURE__*/React.createElement("option", {
      key: a.id,
      value: a.handle
    }, "@", a.handle))), /*#__PURE__*/React.createElement(Button, {
      type: "submit",
      size: "sm",
      style: {
        padding: '6px 12px'
      }
    }, "Criar"))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 16,
      padding: '16px 24px',
      overflowX: 'auto',
      flex: 1
    }
  }, D.statusOrder.map(s => {
    const items = issues.filter(i => i.status === s);
    return /*#__PURE__*/React.createElement(BoardColumn, {
      key: s,
      title: D.statusTitles[s],
      count: items.length
    }, items.map(i => /*#__PURE__*/React.createElement(IssueCard, {
      key: i.key,
      issueKey: i.key,
      title: i.title,
      priority: i.priority,
      assignee: i.assignee,
      onClick: () => openIssue(i)
    })));
  })));
}

/* ── Issue detail ──────────────────────────────────────────── */
function IssueScreen({
  issue,
  back,
  patch
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    IssueCard,
    BoardColumn,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [comments, setComments] = React.useState([{
    author: 'agent',
    body: 'Reproduzi o travamento: o runner não trata exit != 0 do subprocess. Vou cobrir com teste antes do fix.',
    at: '24/07 09:05'
  }, {
    author: 'system',
    body: 'task:running · /data/workspaces/RYU-142',
    at: '24/07 09:12'
  }]);
  const [draft, setDraft] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: '24px',
      display: 'grid',
      gridTemplateColumns: '1fr var(--issue-sidebar-width)',
      gap: 32
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      back();
    },
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-left",
    size: 12
  }), " Board"), /*#__PURE__*/React.createElement(IssueKey, null, issue.key), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      padding: '2px 6px',
      borderRadius: 'var(--radius-full)',
      border: '1px solid var(--border-strong)',
      color: 'var(--text-accent)'
    }
  }, "runner")), /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: '0 0 12px',
      fontSize: 'var(--text-2xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)',
      textWrap: 'pretty'
    }
  }, issue.title), /*#__PURE__*/React.createElement(Card, {
    tone: "muted",
    pad: 16,
    style: {
      marginBottom: 24,
      fontSize: 'var(--text-sm)',
      color: 'var(--text-secondary)',
      whiteSpace: 'pre-wrap'
    }
  }, `O runner despacha a CLI do agente com subprocess e assume exit 0.
Quando a CLI falha, a task fica presa em "running" e o hub nunca publica task:failed.`), /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-muted)'
    }
  }, "Coment\xE1rios"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, comments.map((c, i) => /*#__PURE__*/React.createElement(Card, {
    key: i,
    tone: "muted",
    pad: 12
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-medium)',
      color: c.author === 'agent' ? 'var(--text-accent)' : c.author === 'system' ? 'var(--text-subtle)' : 'var(--text-secondary)',
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4
    }
  }, c.author === 'agent' ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "bot",
    size: 12
  }), " agent") : c.author === 'system' ? 'sistema' : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Icon, {
    name: "user",
    size: 12
  }), " member")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-11)',
      color: 'var(--text-faint)'
    }
  }, c.at)), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      whiteSpace: 'pre-wrap'
    }
  }, c.body)))), /*#__PURE__*/React.createElement("form", {
    style: {
      marginTop: 16
    },
    onSubmit: e => {
      e.preventDefault();
      if (!draft.trim()) return;
      setComments([...comments, {
        author: 'member',
        body: draft,
        at: 'agora'
      }]);
      setDraft('');
    }
  }, /*#__PURE__*/React.createElement(Textarea, {
    rows: 3,
    placeholder: "Escreva um coment\xE1rio...",
    value: draft,
    onChange: e => setDraft(e.target.value)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      display: 'flex',
      justifyContent: 'flex-end'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    type: "submit"
  }, "Comentar")))), /*#__PURE__*/React.createElement("aside", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, [['Status', D.statusOrder.map(s => [s, D.statusTitles[s]]), issue.status, 'status'], ['Prioridade', ['urgent', 'high', 'medium', 'low', 'none'].map(p => [p, p]), issue.priority, 'priority']].map(([label, opts, val, key]) => /*#__PURE__*/React.createElement("div", {
    key: key
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 4,
      fontSize: 'var(--text-11)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wide)',
      color: 'var(--text-subtle)'
    }
  }, label), /*#__PURE__*/React.createElement(Select, {
    full: true,
    value: val,
    onChange: e => patch(issue.key, key, e.target.value)
  }, opts.map(([v, l]) => /*#__PURE__*/React.createElement("option", {
    key: v,
    value: v
  }, l))))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 4,
      fontSize: 'var(--text-11)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wide)',
      color: 'var(--text-subtle)'
    }
  }, "Agente"), /*#__PURE__*/React.createElement(Select, {
    full: true,
    value: issue.assignee || '',
    onChange: e => patch(issue.key, 'assignee', e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "Sem assignee"), D.agents.map(a => /*#__PURE__*/React.createElement("option", {
    key: a.id,
    value: a.handle
  }, "@", a.handle)))), /*#__PURE__*/React.createElement("div", {
    style: {
      paddingTop: 8,
      borderTop: '1px solid var(--border-default)',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0
    }
  }, "Criada: 21/07/2026 11:04"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0
    }
  }, "Atualizada: 24/07/2026 09:12"), issue.assignee && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      color: 'var(--text-accent)',
      display: 'flex',
      alignItems: 'center',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bot",
    size: 12
  }), " Assignee: ", issue.assignee))));
}
Object.assign(window, {
  BoardScreen,
  IssueScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/Screens.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/Screens2.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* ── Dashboard ─────────────────────────────────────────────── */
function DashboardScreen({
  issues,
  go
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 32
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, D.workspace.name), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '2px 0 0',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-subtle)'
    }
  }, "Vis\xE3o geral do workspace")), /*#__PURE__*/React.createElement(Button, {
    onClick: () => go('board')
  }, "Ir para o Board")), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 12px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-muted)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wider)'
    }
  }, "Issues"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(7, 1fr)',
      gap: 12
    }
  }, D.statusOrder.map(s => /*#__PURE__*/React.createElement(StatCard, {
    key: s,
    hoverable: true,
    value: issues.filter(i => i.status === s).length,
    label: D.statusTitles[s],
    status: s,
    style: {
      cursor: 'pointer'
    },
    onClick: () => go('board')
  })))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: 0,
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-muted)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wider)'
    }
  }, "Agents"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      go('agents');
    },
    style: {
      fontSize: 'var(--text-xs)'
    }
  }, "ver todos")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: 12
    }
  }, D.agents.map(a => /*#__PURE__*/React.createElement(AgentCard, _extends({
    key: a.id,
    compact: true
  }, a))))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 12px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-muted)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wider)'
    }
  }, "Tasks recentes"), /*#__PURE__*/React.createElement(DataTable, {
    columns: [{
      key: 'agent',
      label: 'Agente'
    }, {
      key: 'kind',
      label: 'Tipo',
      muted: true
    }, {
      key: 'status',
      label: 'Status'
    }, {
      key: 'summary',
      label: 'Resumo',
      muted: true,
      maxWidth: 280
    }, {
      key: 'at',
      label: 'Criada',
      align: 'right',
      small: true,
      muted: true
    }],
    rows: D.tasks.map(t => ({
      ...t,
      status: /*#__PURE__*/React.createElement(StatusPill, {
        kind: "task",
        status: t.status
      })
    })),
    empty: "Nenhuma task executada ainda."
  })));
}

/* ── Chat ──────────────────────────────────────────────────── */
function ChatScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [messages, setMessages] = React.useState(D.messages);
  const [draft, setDraft] = React.useState('');
  const [active, setActive] = React.useState(0);
  const sessions = [{
    title: 'RYU-142 · travamento do runner',
    pinned: true
  }, {
    title: 'Plano de migração p/ Postgres'
  }, {
    title: 'Revisão do CONTRACTS.md'
  }];
  const typing = messages[messages.length - 1] && messages[messages.length - 1].role === 'user';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 'var(--chat-list-width)',
      flexShrink: 0,
      borderRight: '1px solid var(--border-default)',
      background: 'var(--chat-list-bg)',
      display: 'flex',
      flexDirection: 'column'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 12,
      borderBottom: '1px solid var(--border-default)',
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Select, {
    full: true
  }, D.agents.map(a => /*#__PURE__*/React.createElement("option", {
    key: a.id
  }, a.name, " (", a.handle, ")"))), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    style: {
      padding: '6px 12px'
    }
  }, "Novo")), /*#__PURE__*/React.createElement("nav", {
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: '8px 4px'
    }
  }, sessions.map((s, i) => /*#__PURE__*/React.createElement("a", {
    key: i,
    href: "#",
    onClick: e => {
      e.preventDefault();
      setActive(i);
    },
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 12px',
      margin: '0 4px',
      borderRadius: 'var(--radius-md)',
      fontSize: 'var(--text-sm)',
      textDecoration: 'none',
      background: active === i ? 'var(--surface-active)' : 'transparent',
      color: active === i ? 'var(--text-primary)' : 'var(--text-muted)'
    }
  }, s.pinned && /*#__PURE__*/React.createElement(Icon, {
    name: "star",
    size: 12,
    style: {
      color: 'var(--amber-500)'
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, s.title))))), /*#__PURE__*/React.createElement("section", {
    style: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--chat-panel-bg)',
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '12px 16px',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-primary)'
    }
  }, sessions[active].title), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--amber-500)',
      cursor: 'pointer',
      display: 'inline-flex'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "star",
    size: 16
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-subtle)',
      cursor: 'pointer',
      display: 'inline-flex'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "archive",
    size: 16
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, messages.map((m, i) => /*#__PURE__*/React.createElement(ChatBubble, {
    key: i,
    role: m.role,
    time: m.time
  }, m.content)), typing && /*#__PURE__*/React.createElement(ChatBubble, {
    typing: true
  }, "agente digitando\u2026")), /*#__PURE__*/React.createElement("footer", {
    style: {
      padding: 12,
      borderTop: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("form", {
    style: {
      display: 'flex',
      gap: 8
    },
    onSubmit: e => {
      e.preventDefault();
      if (!draft.trim()) return;
      setMessages(m => [...m, {
        role: 'user',
        content: draft,
        time: 'agora'
      }]);
      setDraft('');
      setTimeout(() => setMessages(m => [...m, {
        role: 'agent',
        content: 'Anotado. Abrindo a issue e enfileirando a task.',
        time: 'agora'
      }]), 1200);
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "Mensagem para o agente\u2026",
    value: draft,
    onChange: e => setDraft(e.target.value),
    style: {
      background: 'var(--surface-input)',
      borderColor: 'var(--border-strong)',
      borderRadius: 'var(--radius-lg)',
      padding: '8px 12px'
    }
  }), /*#__PURE__*/React.createElement(Button, {
    type: "submit",
    size: "lg",
    style: {
      borderRadius: 'var(--radius-lg)'
    }
  }, "Enviar")))));
}

/* ── Inbox ─────────────────────────────────────────────────── */
function InboxScreen({
  items,
  markRead,
  markAll
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const unread = items.filter(i => !i.read).length;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Inbox",
    right: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Select, {
      size: "sm"
    }, /*#__PURE__*/React.createElement("option", null, "Todas severidades"), /*#__PURE__*/React.createElement("option", null, "A\xE7\xE3o necess\xE1ria"), /*#__PURE__*/React.createElement("option", null, "Aten\xE7\xE3o")), /*#__PURE__*/React.createElement(Select, {
      size: "sm"
    }, /*#__PURE__*/React.createElement("option", null, "Todas"), /*#__PURE__*/React.createElement("option", null, "N\xE3o lidas"), /*#__PURE__*/React.createElement("option", null, "Lidas")), /*#__PURE__*/React.createElement(Button, {
      variant: "secondary",
      size: "sm",
      onClick: markAll
    }, "Marcar todas como lidas")),
    kicker: unread ? unread + ' não lidas' : null
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: 'auto'
    }
  }, items.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '48px 24px',
      textAlign: 'center',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-subtle)'
    }
  }, "Inbox vazia. Nada por aqui."), items.map((it, i) => /*#__PURE__*/React.createElement(InboxItem, _extends({
    key: i
  }, it, {
    time: it.at
  }), !it.read && /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    onClick: () => markRead(i)
  }, "Lida"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm"
  }, "Arquivar")))));
}

/* ── Agents ────────────────────────────────────────────────── */
function AgentsScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 32
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Agents"), /*#__PURE__*/React.createElement(Card, {
    tone: "muted",
    pad: 16,
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8,
      alignItems: 'flex-end'
    }
  }, [['Nome', 'Codebot', 140], ['Handle', '@codebot', 140], ['Descrição', 'O que este agente faz', 0]].map(([l, ph, w]) => /*#__PURE__*/React.createElement("div", {
    key: l,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      flex: w ? 'none' : 1,
      width: w || undefined
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, l), /*#__PURE__*/React.createElement(Input, {
    size: "sm",
    tone: "raised",
    placeholder: ph,
    style: {
      background: 'var(--zinc-800)'
    }
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, "Runtime"), /*#__PURE__*/React.createElement(Select, {
    size: "sm",
    style: {
      background: 'var(--zinc-800)'
    }
  }, /*#__PURE__*/React.createElement("option", null, "claude"), /*#__PURE__*/React.createElement("option", null, "codex"), /*#__PURE__*/React.createElement("option", null, "gemini"))), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    style: {
      padding: '6px 16px'
    }
  }, "Criar agente")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: 12
    }
  }, D.agents.map(a => /*#__PURE__*/React.createElement(AgentCard, _extends({
    key: a.id
  }, a)))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-secondary)'
    }
  }, "Tasks recentes"), /*#__PURE__*/React.createElement(DataTable, {
    columns: [{
      key: 'agent',
      label: 'Agente'
    }, {
      key: 'kind',
      label: 'Kind',
      muted: true
    }, {
      key: 'status',
      label: 'Status'
    }, {
      key: 'at',
      label: 'Criada',
      small: true,
      muted: true
    }],
    rows: D.tasks.map(t => ({
      ...t,
      status: /*#__PURE__*/React.createElement(StatusPill, {
        kind: "task",
        status: t.status
      })
    })),
    empty: "Nenhuma task ainda."
  })));
}

/* ── Usage ─────────────────────────────────────────────────── */
function UsageScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA,
    u = D.usage;
  const fmt = n => n.toLocaleString('en-US');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflowY: 'auto'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Usage",
    sub: `Últimos ${u.days} dias — desde 2026-06-25`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 16,
      padding: '24px'
    }
  }, /*#__PURE__*/React.createElement(StatCard, {
    value: u.tasks,
    label: "Tasks"
  }), /*#__PURE__*/React.createElement(StatCard, {
    value: fmt(u.input),
    label: "Input tokens"
  }), /*#__PURE__*/React.createElement(StatCard, {
    value: fmt(u.output),
    label: "Output tokens"
  }), /*#__PURE__*/React.createElement(StatCard, {
    value: '$' + u.cost.toFixed(4),
    label: "Custo (USD)",
    accent: true
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '0 24px 24px'
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Por agente"), /*#__PURE__*/React.createElement(DataTable, {
    bordered: false,
    columns: [{
      key: 'agent',
      label: 'Agente'
    }, {
      key: 'tasks',
      label: 'Tasks'
    }, {
      key: 'i',
      label: 'Input'
    }, {
      key: 'o',
      label: 'Output'
    }, {
      key: 'c',
      label: 'Custo'
    }, {
      key: 's',
      label: 'Status',
      small: true,
      muted: true
    }],
    rows: [{
      agent: 'Codebot',
      tasks: 141,
      i: '3,204,881',
      o: '268,110',
      c: '$25.9012',
      s: 'completed: 118 · failed: 9'
    }, {
      agent: 'Reviewer',
      tasks: 52,
      i: '1,102,441',
      o: '88,220',
      c: '$9.4180',
      s: 'completed: 50 · cancelled: 2'
    }, {
      agent: 'Docs',
      tasks: 21,
      i: '505,578',
      o: '35,112',
      c: '$2.9519',
      s: 'completed: 21'
    }]
  })));
}

/* ── Placeholder para telas não recriadas ──────────────────── */
function StubScreen({
  title,
  note
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: title
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24
    }
  }, /*#__PURE__*/React.createElement(EmptyState, null, note)));
}

/* ── Profile ───────────────────────────────────────────────── */
function ProfileScreen({
  user,
  setUser,
  onLogout
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusDot,
    StatusPill,
    PriorityTag,
    CountBadge,
    IssueKey,
    DataTable,
    ChatBubble,
    InboxItem,
    StatCard,
    AgentCard,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const [nickname, setNickname] = React.useState(user.nickname);
  const [email, setEmail] = React.useState(user.email);
  const initials = (user.nickname || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--form-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Perfil"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 20,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 64,
      height: 64,
      borderRadius: 'var(--radius-full)',
      background: 'var(--surface-active)',
      color: 'var(--text-secondary)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      flexShrink: 0
    }
  }, initials), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Button, {
    variant: "outline",
    size: "sm"
  }, "Trocar foto"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '6px 0 0',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "PNG ou JPG, at\xE9 2MB. Sem foto, usamos as iniciais do apelido."))), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 20,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 4,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, "Apelido"), /*#__PURE__*/React.createElement(Input, {
    value: nickname,
    onChange: e => setNickname(e.target.value)
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 4,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, "E-mail"), /*#__PURE__*/React.createElement(Input, {
    type: "email",
    value: email,
    onChange: e => setEmail(e.target.value)
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Button, {
    onClick: () => setUser(u => ({
      ...u,
      nickname,
      email
    }))
  }, "Salvar"))), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 20
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: onLogout
  }, "Sair da conta")));
}
Object.assign(window, {
  DashboardScreen,
  ChatScreen,
  InboxScreen,
  AgentsScreen,
  UsageScreen,
  StubScreen,
  ProfileScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/Screens2.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/Screens3.jsx
try { (() => {
/* ── Projects ──────────────────────────────────────────────── */
function ProjectsScreen({
  open
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    Icon,
    StatusPill,
    DataTable
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [projects, setProjects] = React.useState(D.projects);
  const [name, setName] = React.useState('');
  const [desc, setDesc] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Projects",
    sub: projects.length + ' projeto(s)'
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24
    }
  }, /*#__PURE__*/React.createElement("form", {
    style: {
      display: 'flex',
      gap: 8,
      marginBottom: 24
    },
    onSubmit: e => {
      e.preventDefault();
      if (!name.trim()) return;
      setProjects(p => [...p, {
        id: 'p' + (p.length + 1),
        name,
        description: desc,
        status: 'active'
      }]);
      setName('');
      setDesc('');
    }
  }, /*#__PURE__*/React.createElement(Input, {
    full: false,
    style: {
      width: 220
    },
    placeholder: "Nome do projeto",
    value: name,
    onChange: e => setName(e.target.value)
  }), /*#__PURE__*/React.createElement(Input, {
    full: false,
    style: {
      flex: 1
    },
    placeholder: "Descri\xE7\xE3o (opcional)",
    value: desc,
    onChange: e => setDesc(e.target.value)
  }), /*#__PURE__*/React.createElement(Button, {
    type: "submit"
  }, "Criar projeto")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: 16
    }
  }, projects.map(p => /*#__PURE__*/React.createElement(Card, {
    key: p.id,
    tone: "raised",
    hoverable: true,
    pad: 16,
    style: {
      cursor: 'pointer'
    },
    onClick: () => open(p)
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-primary)'
    }
  }, p.name), /*#__PURE__*/React.createElement(StatusPill, {
    kind: "state",
    status: p.status === 'active' ? 'on' : 'off'
  }, p.status)), p.description && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '4px 0 0',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, p.description), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '8px 0 0',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, D.issueCounts[p.id] || 0, " issue(s)"))), projects.length === 0 && /*#__PURE__*/React.createElement(EmptyState, null, "Nenhum projeto ainda. Crie o primeiro acima."))));
}
function ProjectDetailScreen({
  project,
  issues,
  back
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    Icon,
    StatusPill,
    DataTable
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const items = issues.filter(i => D.issueCounts[project.id] ? true : false).slice(0, D.issueCounts[project.id] || 0);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: 24
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      back();
    },
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "\u2190 Projects"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-lg)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, project.name), /*#__PURE__*/React.createElement(StatusPill, {
    kind: "state",
    status: project.status === 'active' ? 'on' : 'off'
  }, project.status)), project.description && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '4px 0 0',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-subtle)'
    }
  }, project.description), /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '24px 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Issues (", items.length, ")"), /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden'
    }
  }, items.map(i => /*#__PURE__*/React.createElement("div", {
    key: i.key,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 16px',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-key)',
      color: 'var(--text-subtle)',
      width: 70,
      flexShrink: 0
    }
  }, i.key), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, i.title), /*#__PURE__*/React.createElement(StatusPill, {
    kind: "task",
    status: "queued"
  }, D.statusTitles[i.status]))), items.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24,
      textAlign: 'center',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-subtle)'
    }
  }, "Nenhuma issue neste projeto.")));
}

/* ── Runtimes ──────────────────────────────────────────────── */
function RuntimesScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    Icon,
    StatusPill,
    DataTable
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Runtimes",
    sub: "CLIs detectados no servidor onde o Ryu roda."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24
    }
  }, /*#__PURE__*/React.createElement(DataTable, {
    columns: [{
      key: 'name',
      label: 'Runtime',
      mono: true
    }, {
      key: 'status',
      label: 'Status'
    }, {
      key: 'path',
      label: 'Caminho',
      muted: true,
      mono: true
    }],
    rows: D.runtimes.map(r => ({
      name: r.name,
      status: /*#__PURE__*/React.createElement(StatusPill, {
        kind: "state",
        status: r.available ? 'on' : 'off'
      }, r.available ? 'disponível' : 'indisponível'),
      path: r.path || '—'
    }))
  }), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      marginTop: 24,
      maxWidth: 640,
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '0 0 4px',
      color: 'var(--text-secondary)',
      fontWeight: 'var(--weight-medium)'
    }
  }, "Como configurar"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0
    }
  }, "Instale o CLI desejado no host e garanta que ele esteja no ", /*#__PURE__*/React.createElement("code", {
    style: {
      color: 'var(--text-accent)'
    }
  }, "PATH"), " do processo do Ryu. Cada agent usa o campo ", /*#__PURE__*/React.createElement("code", {
    style: {
      color: 'var(--text-accent)'
    }
  }, "runtime"), " (claude|codex|gemini)."))));
}

/* ── Settings ──────────────────────────────────────────────── */
function SettingsScreen({
  onLogout
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    Icon,
    StatusPill,
    DataTable
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [name, setName] = React.useState(D.workspace.name);
  const [prefix, setPrefix] = React.useState(D.workspace.prefix);
  const [tokens, setTokens] = React.useState(D.patTokens);
  const [tokName, setTokName] = React.useState('');
  const [newTok, setNewTok] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--form-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-lg)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Settings"), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Workspace"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 4,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "Nome do workspace"), /*#__PURE__*/React.createElement(Input, {
    value: name,
    onChange: e => setName(e.target.value)
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 4,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "Issue prefix"), /*#__PURE__*/React.createElement(Input, {
    value: prefix,
    onChange: e => setPrefix(e.target.value.toUpperCase()),
    style: {
      width: 120,
      fontFamily: 'var(--font-mono)',
      textTransform: 'uppercase'
    }
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Button, {
    size: "sm"
  }, "Salvar")))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Personal Access Tokens (ryu_)"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "Nome do token (ex.: cli local)",
    value: tokName,
    onChange: e => setTokName(e.target.value)
  }), /*#__PURE__*/React.createElement(Button, {
    onClick: () => {
      setTokens(t => [...t, {
        id: 't' + (t.length + 1),
        name: tokName || '(sem nome)',
        created: '26/07/2026'
      }]);
      setNewTok('ryu_' + Math.random().toString(36).slice(2, 18));
      setTokName('');
    }
  }, "Criar token")), newTok && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      fontFamily: 'var(--font-mono)',
      color: 'var(--emerald-500)',
      border: '1px solid var(--emerald-500)',
      borderRadius: 'var(--radius-md)',
      padding: 12,
      wordBreak: 'break-all'
    }
  }, "Copie agora (exibido uma \xFAnica vez): ", newTok), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, tokens.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '8px 0',
      borderTop: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-secondary)'
    }
  }, t.name, " ", /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "\xB7 ", t.created)), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: () => setTokens(ts => ts.filter(x => x.id !== t.id))
  }, "Revogar"))), tokens.length === 0 && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '8px 0 0',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "Nenhum token ativo.")))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Sess\xE3o"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    onClick: onLogout
  }, "Sair (logout)"))));
}

/* ── My Issues ─────────────────────────────────────────────── */
function MyIssuesScreen({
  issues,
  openIssue
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    Icon,
    StatusPill,
    DataTable
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const mine = issues.filter(i => i.assignee);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: "My Issues",
    sub: mine.length + ' issue(s) atribuída(s) a você'
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, D.statusOrder.map(s => {
    const items = mine.filter(i => i.status === s);
    if (!items.length) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: s
    }, /*#__PURE__*/React.createElement("h2", {
      style: {
        margin: '0 0 8px',
        fontSize: 'var(--text-2xs)',
        textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-wider)',
        color: 'var(--text-subtle)'
      }
    }, D.statusTitles[s], " (", items.length, ")"), /*#__PURE__*/React.createElement("div", {
      style: {
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden'
      }
    }, items.map(i => /*#__PURE__*/React.createElement("div", {
      key: i.key,
      onClick: () => openIssue(i),
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 16px',
        borderBottom: '1px solid var(--border-hairline)',
        cursor: 'pointer'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        font: 'var(--type-key)',
        color: 'var(--text-subtle)',
        width: 70,
        flexShrink: 0
      }
    }, i.key), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        fontSize: 'var(--text-sm)',
        color: 'var(--text-body)'
      }
    }, i.title), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 'var(--text-2xs)',
        textTransform: 'uppercase',
        background: 'var(--surface-active)',
        color: 'var(--text-muted)',
        borderRadius: 'var(--radius-sm)',
        padding: '2px 6px'
      }
    }, i.priority)))));
  }), mine.length === 0 && /*#__PURE__*/React.createElement(EmptyState, null, "Nenhuma issue atribu\xEDda a voc\xEA neste workspace.")));
}
Object.assign(window, {
  ProjectsScreen,
  ProjectDetailScreen,
  RuntimesScreen,
  SettingsScreen,
  MyIssuesScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/Screens3.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/Screens4.jsx
try { (() => {
/* ── Autopilots ────────────────────────────────────────────── */
function AutopilotsScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusPill,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [items, setItems] = React.useState(D.autopilots);
  const [name, setName] = React.useState('');
  const [trigger, setTrigger] = React.useState('cron');
  const [cron, setCron] = React.useState('');
  const [agent, setAgent] = React.useState('');
  const [rule, setRule] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Autopilots"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "Nome do autopilot",
    value: name,
    onChange: e => setName(e.target.value)
  }), /*#__PURE__*/React.createElement(Select, {
    value: trigger,
    onChange: e => setTrigger(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "cron"
  }, "cron"), /*#__PURE__*/React.createElement("option", {
    value: "webhook"
  }, "webhook"), /*#__PURE__*/React.createElement("option", {
    value: "manual"
  }, "manual")), /*#__PURE__*/React.createElement(Input, {
    placeholder: "Cron (ex: 0 9 * * 1-5)",
    value: cron,
    onChange: e => setCron(e.target.value),
    disabled: trigger !== 'cron'
  }), /*#__PURE__*/React.createElement(Select, {
    value: agent,
    onChange: e => setAgent(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "\u2014 sem agente (issue vai p/ backlog) \u2014"), D.agents.map(a => /*#__PURE__*/React.createElement("option", {
    key: a.id,
    value: a.handle
  }, a.name)))), /*#__PURE__*/React.createElement(Textarea, {
    rows: 3,
    placeholder: "Regra / instru\xE7\xE3o \u2014 vira a descri\xE7\xE3o da issue criada em cada run\u2026",
    value: rule,
    onChange: e => setRule(e.target.value)
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Button, {
    onClick: () => {
      if (!name.trim()) return;
      setItems(p => [...p, {
        id: 'ap' + (p.length + 1),
        name,
        trigger_type: trigger,
        cron_expr: cron,
        enabled: true,
        target_agent: agent,
        rule
      }]);
      setName('');
      setRule('');
      setCron('');
      setAgent('');
    }
  }, "Criar autopilot"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, items.map(ap => /*#__PURE__*/React.createElement(Card, {
    key: ap.id,
    tone: "raised",
    pad: 16
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-primary)'
    }
  }, ap.name), /*#__PURE__*/React.createElement(StatusPill, {
    kind: "state",
    status: ap.enabled ? 'on' : 'off'
  }, ap.enabled ? 'ativo' : 'pausado'), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      background: 'var(--surface-active)',
      color: 'var(--text-muted)',
      borderRadius: 'var(--radius-full)',
      padding: '2px 8px'
    }
  }, ap.trigger_type), ap.cron_expr && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-subtle)'
    }
  }, ap.cron_expr)), ap.rule && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 4
    }
  }, ap.rule), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      marginTop: 4
    }
  }, "agente: ", ap.target_agent || '—', ap.webhook_token && /*#__PURE__*/React.createElement(React.Fragment, null, " \xB7 webhook: ", /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: 'var(--font-mono)'
    }
  }, "/api/autopilots/hook/", ap.webhook_token)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "link"
  }, "rodar agora"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    onClick: () => setItems(p => p.map(x => x.id === ap.id ? {
      ...x,
      enabled: !x.enabled
    } : x))
  }, ap.enabled ? 'pausar' : 'ativar'), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: () => setItems(p => p.filter(x => x.id !== ap.id))
  }, "excluir"))))), items.length === 0 && /*#__PURE__*/React.createElement(EmptyState, null, "Nenhum autopilot ainda.")));
}

/* ── Skills ────────────────────────────────────────────────── */
function SkillsScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusPill,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [items, setItems] = React.useState(D.skills);
  const [name, setName] = React.useState('');
  const [desc, setDesc] = React.useState('');
  const [content, setContent] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Skills"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "Nome da skill",
    value: name,
    onChange: e => setName(e.target.value)
  }), /*#__PURE__*/React.createElement(Input, {
    placeholder: "Descri\xE7\xE3o curta",
    value: desc,
    onChange: e => setDesc(e.target.value)
  })), /*#__PURE__*/React.createElement(Textarea, {
    mono: true,
    rows: 4,
    placeholder: "Conte\xFAdo em markdown\u2026",
    value: content,
    onChange: e => setContent(e.target.value)
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Button, {
    onClick: () => {
      if (!name.trim()) return;
      setItems(p => [...p, {
        id: 's' + (p.length + 1),
        name,
        description: desc,
        content,
        attached: []
      }]);
      setName('');
      setDesc('');
      setContent('');
    }
  }, "Criar skill"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, items.map(s => /*#__PURE__*/React.createElement(Card, {
    key: s.id,
    tone: "raised",
    pad: 16
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-primary)'
    }
  }, s.name), s.description && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)'
    }
  }, s.description)), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: () => setItems(p => p.filter(x => x.id !== s.id))
  }, "excluir")), s.content && /*#__PURE__*/React.createElement("pre", {
    style: {
      marginTop: 8,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      background: 'var(--surface-sunken)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      padding: 8,
      overflowX: 'auto',
      maxHeight: 120,
      fontFamily: 'var(--font-mono)'
    }
  }, s.content), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12,
      display: 'flex',
      flexWrap: 'wrap',
      alignItems: 'center',
      gap: 8
    }
  }, (s.attached || []).map(a => /*#__PURE__*/React.createElement("span", {
    key: a,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      background: 'var(--surface-active)',
      color: 'var(--text-secondary)',
      fontSize: 'var(--text-xs)',
      borderRadius: 'var(--radius-full)',
      padding: '2px 8px'
    }
  }, a, " ", /*#__PURE__*/React.createElement("span", {
    style: {
      cursor: 'pointer',
      color: 'var(--text-subtle)'
    },
    onClick: () => setItems(p => p.map(x => x.id === s.id ? {
      ...x,
      attached: x.attached.filter(y => y !== a)
    } : x))
  }, "\xD7"))), /*#__PURE__*/React.createElement(Button, {
    variant: "link"
  }, "+ agente")))), items.length === 0 && /*#__PURE__*/React.createElement(EmptyState, null, "Nenhuma skill ainda.")));
}

/* ── Squads ────────────────────────────────────────────────── */
function SquadsScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusPill,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [items, setItems] = React.useState(D.squads);
  const [name, setName] = React.useState('');
  const [leader, setLeader] = React.useState(D.agents[0]?.handle || '');
  const [desc, setDesc] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xl)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Squads"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "Nome da squad",
    value: name,
    onChange: e => setName(e.target.value)
  }), /*#__PURE__*/React.createElement(Select, {
    value: leader,
    onChange: e => setLeader(e.target.value)
  }, D.agents.map(a => /*#__PURE__*/React.createElement("option", {
    key: a.id,
    value: a.handle
  }, "l\xEDder: ", a.name))), /*#__PURE__*/React.createElement(Button, {
    onClick: () => {
      if (!name.trim()) return;
      setItems(p => [...p, {
        id: 'sq' + (p.length + 1),
        name,
        leader,
        description: desc,
        instructions: '',
        members: [[leader, 'líder']]
      }]);
      setName('');
      setDesc('');
    }
  }, "Criar squad")), /*#__PURE__*/React.createElement(Input, {
    placeholder: "Descri\xE7\xE3o (o que a squad faz)",
    value: desc,
    onChange: e => setDesc(e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, items.map(s => /*#__PURE__*/React.createElement(Card, {
    key: s.id,
    tone: "raised",
    pad: 16
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-primary)'
    }
  }, s.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "l\xEDder: ", s.leader), s.description && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      marginTop: 4
    }
  }, s.description)), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: () => setItems(p => p.filter(x => x.id !== s.id))
  }, "excluir")), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8,
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8
    }
  }, s.members.map(([m, role]) => /*#__PURE__*/React.createElement("span", {
    key: m,
    style: {
      background: 'var(--surface-active)',
      color: 'var(--text-secondary)',
      fontSize: 'var(--text-xs)',
      borderRadius: 'var(--radius-full)',
      padding: '2px 8px'
    }
  }, m, " ", role === 'líder' ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--amber-500)'
    }
  }, "\u2605") : /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-subtle)'
    }
  }, "\xB7 ", role)))))), items.length === 0 && /*#__PURE__*/React.createElement(EmptyState, null, "Nenhuma squad ainda.")));
}

/* ── Members ───────────────────────────────────────────────── */
function MembersScreen() {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusPill,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  const [members, setMembers] = React.useState(D.members);
  const [invites, setInvites] = React.useState(D.invitations);
  const [email, setEmail] = React.useState('');
  const [role, setRole] = React.useState('member');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--form-max)',
      margin: '0 auto',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 'var(--text-lg)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-primary)'
    }
  }, "Members"), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Convidar membro"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 16,
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "email@exemplo.com",
    value: email,
    onChange: e => setEmail(e.target.value)
  }), /*#__PURE__*/React.createElement(Select, {
    value: role,
    onChange: e => setRole(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "member"
  }, "member"), /*#__PURE__*/React.createElement("option", {
    value: "admin"
  }, "admin")), /*#__PURE__*/React.createElement(Button, {
    onClick: () => {
      if (!email.trim()) return;
      setInvites(p => [...p, {
        id: 'i' + (p.length + 1),
        email,
        role,
        expires: '02/09/2026'
      }]);
      setEmail('');
    }
  }, "Convidar"))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Membros (", members.length, ")"), /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 0,
    style: {
      overflow: 'hidden'
    }
  }, members.map(m => /*#__PURE__*/React.createElement("div", {
    key: m.id,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 16px',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, m.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, m.email)), m.you ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-subtle)'
    }
  }, m.role) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Select, {
    value: m.role,
    onChange: e => setMembers(p => p.map(x => x.id === m.id ? {
      ...x,
      role: e.target.value
    } : x)),
    style: {
      fontSize: 'var(--text-xs)'
    }
  }, /*#__PURE__*/React.createElement("option", {
    value: "owner"
  }, "owner"), /*#__PURE__*/React.createElement("option", {
    value: "admin"
  }, "admin"), /*#__PURE__*/React.createElement("option", {
    value: "member"
  }, "member")), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: () => setMembers(p => p.filter(x => x.id !== m.id))
  }, "remover")))))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: '0 0 8px',
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--weight-medium)',
      color: 'var(--text-secondary)'
    }
  }, "Convites pendentes (", invites.length, ")"), invites.length ? /*#__PURE__*/React.createElement(Card, {
    tone: "raised",
    pad: 0,
    style: {
      overflow: 'hidden'
    }
  }, invites.map(inv => /*#__PURE__*/React.createElement("div", {
    key: inv.id,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 16px',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, inv.email), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "papel: ", inv.role, " \xB7 expira ", inv.expires)), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    onClick: () => setInvites(p => p.filter(x => x.id !== inv.id))
  }, "revogar")))) : /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, "Nenhum convite pendente.")));
}

/* ── Search ────────────────────────────────────────────────── */
function SearchScreen({
  query,
  setQuery,
  issues
}) {
  const {
    Button,
    Input,
    Select,
    Textarea,
    Card,
    EmptyState,
    StatusPill,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const q = (query || '').toLowerCase();
  const results = q ? issues.filter(i => i.title.toLowerCase().includes(q) || i.key.toLowerCase().includes(q)) : [];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }
  }, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Search"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '0 24px'
    }
  }, /*#__PURE__*/React.createElement(Input, {
    full: false,
    style: {
      width: 420,
      marginTop: 12
    },
    placeholder: "Buscar issues, agents, chats\u2026",
    value: query,
    onChange: e => setQuery(e.target.value),
    autoFocus: true
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24
    }
  }, q && results.length === 0 && /*#__PURE__*/React.createElement(EmptyState, null, "Nenhum resultado para \"", query, "\"."), results.map(i => /*#__PURE__*/React.createElement("div", {
    key: i.key,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 0',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-key)',
      color: 'var(--text-subtle)',
      width: 70
    }
  }, i.key), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, i.title)))));
}
Object.assign(window, {
  AutopilotsScreen,
  SkillsScreen,
  SquadsScreen,
  MembersScreen,
  SearchScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/Screens4.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/Shell.jsx
try { (() => {
const NAV = [{
  group: null,
  items: [['inbox', 'inbox', 'Inbox'], ['chat', 'message-circle', 'Chat'], ['my_issues', 'user', 'My Issues']]
}, {
  group: 'Workspace',
  items: [['board', 'layout-grid', 'Issues'], ['projects', 'folder', 'Projects'], ['autopilots', 'zap', 'Autopilots'], ['agents', 'bot', 'Agents'], ['squads', 'users', 'Squads'], ['usage', 'bar-chart-2', 'Usage']]
}, {
  group: 'Configure',
  items: [['runtimes', 'puzzle', 'Runtimes'], ['skills', 'book-open', 'Skills'], ['members', 'users', 'Members'], ['settings', 'settings', 'Settings']]
}];
function Shell({
  route,
  setRoute,
  unread,
  theme,
  setTheme,
  user,
  query,
  setQuery,
  children
}) {
  const {
    Sidebar,
    SidebarSection,
    NavItem,
    TopBar,
    ThemeToggle,
    Icon
  } = window.RyuDesignSystem_7ed69e;
  const D = window.RYU_DATA;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      height: '100%',
      background: 'var(--surface-app)'
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    user: user,
    onSearch: e => {
      setQuery(e.target.value);
      setRoute('search');
    },
    onProfileClick: () => setRoute('profile')
  }, NAV.map((g, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: i
  }, g.group && /*#__PURE__*/React.createElement(SidebarSection, null, g.group), g.items.map(([key, icon, label]) => /*#__PURE__*/React.createElement(NavItem, {
    key: key,
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: icon,
      size: 15
    }),
    label: label,
    active: route === key,
    count: key === 'inbox' ? unread : 0,
    onClick: e => {
      e.preventDefault();
      setRoute(key);
    }
  }))))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    connection: "connected",
    inboxCount: unread
  }, /*#__PURE__*/React.createElement(ThemeToggle, {
    theme: theme,
    onChange: setTheme
  })), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      overflowY: 'auto',
      minHeight: 0
    }
  }, children)));
}
function PageHeader({
  title,
  sub,
  right,
  kicker
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      padding: '16px 24px',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      font: 'var(--type-page-title)',
      color: 'var(--text-primary)'
    }
  }, title), kicker && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)',
      textTransform: 'uppercase',
      letterSpacing: 'var(--tracking-wide)'
    }
  }, kicker), sub && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-subtle)'
    }
  }, sub)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, right));
}
Object.assign(window, {
  Shell,
  PageHeader
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/Shell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ryu-app/data.js
try { (() => {
window.RYU_DATA = {
  workspace: {
    name: 'Ryu',
    slug: 'ryu',
    prefix: 'RYU'
  },
  user: {
    name: 'Renato Bardi',
    email: 'renato@exemplo.com'
  },
  agents: [{
    id: 'a1',
    name: 'Codebot',
    handle: 'codebot',
    runtime: 'claude',
    status: 'working',
    description: 'Corrige bugs e abre PRs no backend'
  }, {
    id: 'a2',
    name: 'Reviewer',
    handle: 'reviewer',
    runtime: 'codex',
    status: 'idle',
    description: 'Revisa diffs antes do merge'
  }, {
    id: 'a3',
    name: 'Docs',
    handle: 'docs',
    runtime: 'gemini',
    status: 'offline',
    description: 'Mantém README e CONTRACTS'
  }],
  statusOrder: ['backlog', 'todo', 'in_progress', 'in_review', 'done', 'blocked', 'cancelled'],
  statusTitles: {
    backlog: 'Backlog',
    todo: 'Todo',
    in_progress: 'In Progress',
    in_review: 'In Review',
    done: 'Done',
    blocked: 'Blocked',
    cancelled: 'Cancelled'
  },
  issues: [{
    key: 'RYU-142',
    title: 'Runner trava quando a CLI do agente sai com código 1',
    status: 'in_progress',
    priority: 'urgent',
    assignee: 'codebot'
  }, {
    key: 'RYU-140',
    title: 'Migrar o hub realtime para Redis pub/sub',
    status: 'in_progress',
    priority: 'high',
    assignee: 'codebot'
  }, {
    key: 'RYU-138',
    title: 'Integração bidirecional com GitHub Issues',
    status: 'todo',
    priority: 'high',
    assignee: 'reviewer'
  }, {
    key: 'RYU-137',
    title: 'Alembic para migrações em Postgres',
    status: 'todo',
    priority: 'medium'
  }, {
    key: 'RYU-131',
    title: 'Marketplace de skills',
    status: 'backlog',
    priority: 'low'
  }, {
    key: 'RYU-129',
    title: 'Notificações no Slack por canal de agente',
    status: 'backlog',
    priority: 'none'
  }, {
    key: 'RYU-126',
    title: 'Rate limit por workspace no dispatch de tasks',
    status: 'in_review',
    priority: 'medium',
    assignee: 'reviewer'
  }, {
    key: 'RYU-118',
    title: 'Login por código de verificação',
    status: 'done',
    priority: 'high'
  }, {
    key: 'RYU-115',
    title: 'Workspaces isolados em /data/workspaces',
    status: 'done',
    priority: 'medium',
    assignee: 'codebot'
  }, {
    key: 'RYU-109',
    title: 'Adapter do gemini-cli sem binário no PATH',
    status: 'blocked',
    priority: 'medium',
    assignee: 'docs'
  }],
  tasks: [{
    agent: 'Codebot',
    kind: 'issue_work',
    status: 'running',
    summary: 'Rodando pytest em RYU-142',
    at: '24/07 09:12'
  }, {
    agent: 'Reviewer',
    kind: 'review',
    status: 'completed',
    summary: 'Aprovado com 2 comentários',
    at: '24/07 08:40'
  }, {
    agent: 'Codebot',
    kind: 'issue_work',
    status: 'failed',
    summary: 'claude CLI retornou exit 1',
    at: '23/07 22:05'
  }, {
    agent: 'Docs',
    kind: 'chore',
    status: 'queued',
    summary: 'Atualizar CONTRACTS.md',
    at: '23/07 19:31'
  }],
  inbox: [{
    severity: 'action_required',
    title: 'codebot pediu aprovação em RYU-142',
    body: 'Vai alterar o schema da tabela tasks — precisa de review humano.',
    at: '24/07 09:12',
    read: false
  }, {
    severity: 'attention',
    title: 'Task falhou em RYU-142',
    body: 'claude CLI retornou exit 1 no workspace /data/workspaces/RYU-142.',
    at: '23/07 22:05',
    read: false
  }, {
    severity: 'info',
    title: 'reviewer concluiu RYU-126',
    body: 'Aprovado com 2 comentários.',
    at: '23/07 18:44',
    read: true
  }],
  messages: [{
    role: 'agent',
    content: 'Peguei a RYU-142. Reproduzi o travamento: o runner não trata exit != 0 do subprocess.',
    time: '14:01'
  }, {
    role: 'user',
    content: 'Manda ver. Cria um teste que cubra exit 1 antes do fix.',
    time: '14:02'
  }, {
    role: 'system',
    content: 'task:dispatched · workspace /data/workspaces/RYU-142',
    time: '14:02'
  }, {
    role: 'agent',
    content: 'Teste escrito em tests/test_flow.py. Rodando pytest…',
    time: '14:03'
  }],
  usage: {
    days: 30,
    tasks: 214,
    input: 4812900,
    output: 391442,
    cost: 38.2711
  },
  projects: [{
    id: 'p1',
    name: 'Core Runner',
    status: 'active',
    description: 'Dispatcher de tasks e integração com CLIs de agente'
  }, {
    id: 'p2',
    name: 'Integrações',
    status: 'active',
    description: 'GitHub, Slack e webhooks externos'
  }, {
    id: 'p3',
    name: 'Onboarding',
    status: 'archived',
    description: 'Fluxo de convite e primeiro workspace'
  }],
  issueCounts: {
    p1: 6,
    p2: 2,
    p3: 1
  },
  autopilots: [{
    id: 'ap1',
    name: 'Triagem diária',
    trigger_type: 'cron',
    cron_expr: '0 9 * * 1-5',
    enabled: true,
    target_agent: 'codebot',
    rule: 'Revisar issues sem assignee e atribuir ao agente certo com base no título.'
  }, {
    id: 'ap2',
    name: 'Deploy hook',
    trigger_type: 'webhook',
    webhook_token: 'wh_9f2a1c',
    enabled: true,
    target_agent: 'reviewer',
    rule: 'Ao receber webhook de deploy, abrir issue de smoke test.'
  }, {
    id: 'ap3',
    name: 'Limpeza de backlog',
    trigger_type: 'manual',
    enabled: false,
    target_agent: null,
    rule: 'Fechar issues de backlog com mais de 90 dias sem atividade.'
  }],
  skills: [{
    id: 's1',
    name: 'Revisão de PR',
    description: 'Checklist de estilo e testes antes de aprovar',
    content: '# Revisão\\n- Rodar lint\\n- Checar testes\\n- Validar migrations',
    attached: ['codebot', 'reviewer']
  }, {
    id: 's2',
    name: 'Runbook de incidente',
    description: 'Passos para triagem de falha em produção',
    content: '1. Checar logs\\n2. Isolar workspace\\n3. Abrir issue urgent',
    attached: ['docs']
  }],
  squads: [{
    id: 'sq1',
    name: 'Backend Squad',
    leader: 'codebot',
    description: 'Cuida do runner e da API',
    instructions: 'Sempre rodar testes antes de abrir PR.',
    members: [['codebot', 'líder'], ['reviewer', 'revisor']]
  }],
  runtimes: [{
    name: 'claude',
    available: true,
    path: '/usr/local/bin/claude'
  }, {
    name: 'codex',
    available: true,
    path: '/usr/local/bin/codex'
  }, {
    name: 'gemini',
    available: false,
    path: null
  }],
  members: [{
    id: 'm1',
    name: 'Renato Bardi',
    email: 'renato@exemplo.com',
    role: 'owner',
    you: true
  }, {
    id: 'm2',
    name: 'Ana Souza',
    email: 'ana@exemplo.com',
    role: 'admin'
  }, {
    id: 'm3',
    name: 'Bruno Lima',
    email: 'bruno@exemplo.com',
    role: 'member'
  }],
  invitations: [{
    id: 'i1',
    email: 'novo@exemplo.com',
    role: 'member',
    expires: '02/08/2026'
  }],
  patTokens: [{
    id: 't1',
    name: 'cli local',
    created: '20/07/2026'
  }]
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ryu-app/data.js", error: String((e && e.message) || e) }); }

__ds_ns.AgentCard = __ds_scope.AgentCard;

__ds_ns.BoardColumn = __ds_scope.BoardColumn;

__ds_ns.ChatBubble = __ds_scope.ChatBubble;

__ds_ns.InboxItem = __ds_scope.InboxItem;

__ds_ns.IssueCard = __ds_scope.IssueCard;

__ds_ns.NavItem = __ds_scope.NavItem;

__ds_ns.Sidebar = __ds_scope.Sidebar;

__ds_ns.SidebarSection = __ds_scope.SidebarSection;

__ds_ns.StatCard = __ds_scope.StatCard;

__ds_ns.TopBar = __ds_scope.TopBar;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.EmptyState = __ds_scope.EmptyState;

__ds_ns.Icon = __ds_scope.Icon;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.ThemeToggle = __ds_scope.ThemeToggle;

__ds_ns.CountBadge = __ds_scope.CountBadge;

__ds_ns.DataTable = __ds_scope.DataTable;

__ds_ns.IssueKey = __ds_scope.IssueKey;

__ds_ns.PriorityTag = __ds_scope.PriorityTag;

__ds_ns.StatusDot = __ds_scope.StatusDot;

__ds_ns.StatusPill = __ds_scope.StatusPill;

})();
