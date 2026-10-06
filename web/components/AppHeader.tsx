import Link from "next/link";
import { Icon, Logo } from "@/components/ui";
import { AccountMenu } from "@/components/AccountMenu";

/** Shared by the app header and the public header of the pricing page, so moving between them nothing shifts. */
export const HEADER_CLS = "flex items-center gap-3 border-b border-line px-4 py-3 sm:gap-4 sm:px-6";

const Slash = () => <span className="shrink-0 text-lg text-line-3" aria-hidden>/</span>;

/** Header of every app page (dashboard, account, bot workspace). The logo goes home to the landing page,
 *  as on every page; `crumb` (a bot's name) follows a «داشبورد» link as a breadcrumb back to the bot list;
 *  `children` sit before the account menu. On phones a bot page drops the logo: a back arrow to the dashboard
 *  and the bot's name are what fits next to its buttons. */
export function AppHeader({ crumb, children }: { crumb?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header className={HEADER_CLS}>
      {crumb ? <div className="hidden sm:block"><Logo size="sm" /></div> : <Logo size="sm" />}
      {crumb ? (
        <nav aria-label="مسیر" className="flex min-w-0 flex-1 basis-0 items-center gap-2 sm:gap-3">
          <span className="hidden sm:contents"><Slash /></span>
          <Link href="/bots/" aria-label="داشبورد" className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-xl border border-line-2 text-fg-2 hover:text-fg sm:min-w-0 sm:border-0 sm:text-sm">
            <Icon name="back" size={18} className="sm:hidden" />
            <span className="hidden sm:inline">داشبورد</span>
          </Link>
          <span className="hidden sm:contents"><Slash /></span>
          <div className="flex min-w-0 flex-col" aria-current="page">{crumb}</div>
        </nav>
      ) : <span className="flex-1" />}
      {children}
      <AccountMenu />
    </header>
  );
}
