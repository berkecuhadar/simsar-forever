import { COLUMNS, CRAFT_COLUMNS, GLOSSARY } from "../strings";

export default function Glossary() {
  return (
    <section>
      <div className="page-head">
        <h1>Glossary</h1>
        <p className="lead">The economic terms used in Simsar, in plain language.</p>
      </div>
      <div className="card">
        <dl className="glossary">
          {GLOSSARY.map((g) => (
            <div key={g.term}>
              <dt>{g.term}</dt>
              <dd>{g.text}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="grid-2">
        <div className="card">
          <h3>Item table columns</h3>
          <dl className="glossary compact">
            {Object.entries(COLUMNS).map(([k, c]) => (
              <div key={k}><dt>{c.title}</dt><dd>{c.hint}</dd></div>
            ))}
          </dl>
        </div>
        <div className="card">
          <h3>Craft table columns</h3>
          <dl className="glossary compact">
            {Object.entries(CRAFT_COLUMNS).map(([k, c]) => (
              <div key={k}><dt>{c.title}</dt><dd>{c.hint}</dd></div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
