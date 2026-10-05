import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { httpStatus } from "../api/client";
import { getLegalDoc, getLegalIndex } from "../api/legal";
import { LEGAL_NAV, PublicLayout } from "../components/PublicLayout";
import { ErrorState, Loading } from "../components/ui";
import { usePageTitle } from "../pageTitle";

/**
 * Документы (пакет L, L5): оферта, политика обработки ПД, согласие, реквизиты. Тексты и
 * реквизиты присылает сервер — здесь только показ.
 *
 * Две вещи видны **над** текстом, а не под ним: что это черновик (пока владелец не
 * утвердил редакцию) и каких реквизитов в тексте не хватает. Договор, который читают, не
 * зная этого, обещает больше, чем значит.
 */
export function LegalPage() {
  const { doc = "" } = useParams();
  return doc ? <LegalDocument slug={doc} /> : <LegalIndexView />;
}

function LegalIndexView() {
  usePageTitle("Документы");
  const query = useQuery({ queryKey: ["legal"], queryFn: getLegalIndex });
  return (
    <PublicLayout>
      <h1>Документы</h1>
      {query.isLoading && <Loading text="Загружаем документы…" />}
      {query.isError && <ErrorState text="Документы не загрузились" onRetry={() => void query.refetch()} />}
      {query.data && (
        <>
          {query.data.draft && (
            <div className="legal-draft" role="note">{query.data.draft_note}</div>
          )}
          <ul className="legal-index">
            {query.data.documents.map((d) => (
              <li key={d.slug}>
                <Link to={`/legal/${d.slug}`}>{d.title}</Link>
                <span>{d.summary}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </PublicLayout>
  );
}

function LegalDocument({ slug }: { slug: string }) {
  const query = useQuery({ queryKey: ["legal", slug], queryFn: () => getLegalDoc(slug), retry: false });
  const doc = query.data;
  usePageTitle(doc?.title ?? "Документ");
  return (
    <PublicLayout>
      {query.isLoading && <Loading text="Загружаем документ…" />}
      {query.isError && (
        <>
          <h1 className="sr-only">Документ</h1>
          <ErrorState
            text={httpStatus(query.error) === 404 ? "Такого документа нет" : "Документ не загрузился"}
            onRetry={httpStatus(query.error) === 404 ? undefined : () => void query.refetch()}
            actions={httpStatus(query.error) === 404
              ? <Link to="/legal" className="btn btn--ghost">Все документы</Link> : undefined}
          />
        </>
      )}
      {doc && (
        <article className="legal-doc">
          <h1>{doc.title}</h1>
          <div className="legal-doc__edition">
            {doc.draft ? "Редакция: черновик" : `Редакция от ${doc.edition}`}
          </div>
          {doc.draft && <div className="legal-draft" role="note">{doc.draft_note}</div>}
          {doc.missing.length > 0 && (
            <div className="legal-missing" role="note">
              В тексте не указано: {doc.missing.join(", ")}. Это реквизиты продавца, которые
              владелец сервиса ещё не задал.
            </div>
          )}
          {doc.sections.map((section) => (
            <section key={section.heading} className="legal-doc__section">
              <h2>{section.heading}</h2>
              {section.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
            </section>
          ))}
          <nav className="legal-doc__more" aria-label="Другие документы">
            {LEGAL_NAV.filter(([to]) => to !== `/legal/${slug}`).map(([to, label]) => (
              <Link key={to} to={to}>{label}</Link>
            ))}
          </nav>
        </article>
      )}
    </PublicLayout>
  );
}
