import { Fragment, type ReactNode } from 'react'

/** Shows the small amount of Markdown an AI answer uses (**bold**, `code`, "- " bullets)
 *  as real formatting. Builds React elements only, never raw HTML, so it is safe. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>
    return <Fragment key={i}>{part}</Fragment>
  })
}

export function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let bullets: string[] = []
  const flush = () => {
    if (bullets.length) {
      blocks.push(<ul key={`ul-${blocks.length}`}>{bullets.map((b, i) => <li key={i}>{inline(b)}</li>)}</ul>)
      bullets = []
    }
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    if (bullet) { bullets.push(bullet[1]); continue }
    flush()
    if (line) blocks.push(<p key={`p-${blocks.length}`}>{inline(line)}</p>)
  }
  flush()
  return <>{blocks}</>
}
