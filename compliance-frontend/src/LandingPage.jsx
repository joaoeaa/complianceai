/**
 * Página pública do ComplianceAI.
 *
 * É a peça de captação: quem chega aqui veio por indicação ou busca e decide em
 * trinta segundos se cria conta. A tese do produto cabe numa frase, "IA que se
 * deixa conferir", e a página inteira se organiza para provar isso em vez de
 * apenas afirmar: o herói mostra um alerta real, com os selos de verificação
 * que o sistema de fato produz, e a comparação com IA genérica é o argumento
 * central, porque é a objeção que decide a conversa com um advogado.
 *
 * Todos os números da página são medidos no banco de produção. Nenhuma
 * afirmação aqui pode prometer o que o código não sustenta: já removemos uma
 * alegação falsa de criptografia e o custo de credibilidade não compensa.
 *
 * A identidade segue o app (dark #0c0f1a, gradiente índigo, DM Sans) para a
 * transição ao entrar não parecer outro produto.
 */
import {
  Shield, ArrowRight, CheckCircle, Scale, Lock, History, Archive,
  AlertTriangle, FileSearch, BookOpen, Landmark, ListChecks,
} from "lucide-react";

const F = "'DM Sans', sans-serif";
const GRAD = "linear-gradient(135deg, #6366f1, #8b5cf6)";
const DARK = "#0c0f1a";

// Números conferidos na base de produção em 12/08/2026. Ao atualizar, recontar:
//   select count(*) from (select distinct d.source, ch.article_ref
//   from legal_chunks ch join legal_documents d on d.id=ch.document_id
//   where ch.article_ref is not null) t
const NUMEROS = [
  { valor: "3.927", rotulo: "artigos de lei indexados", icone: Landmark },
  { valor: "10", rotulo: "leis brasileiras na íntegra", icone: BookOpen },
  { valor: "29", rotulo: "verificações configuráveis", icone: ListChecks },
];

const PASSOS = [
  {
    titulo: "Envie o contrato",
    texto: "PDF ou DOCX, pelo navegador. Documento digitalizado passa por leitura óptica.",
  },
  {
    titulo: "O sistema busca a lei",
    texto: "Busca semântica em 3.927 artigos de dez leis completas, e não na memória do modelo.",
  },
  {
    titulo: "A IA analisa com as suas regras",
    texto: "As 29 verificações padrão mais as que o seu escritório definir, por área do direito.",
  },
  {
    titulo: "Cada alerta é conferido",
    texto: "Trecho localizado no contrato, com a página. Artigo localizado na base. O que não confere vem marcado.",
  },
];

const AREAS = [
  ["5", "Estrutura do contrato"], ["5", "Proteção de dados"], ["5", "Locação"],
  ["3", "Societário"], ["3", "Propriedade industrial"], ["2", "Civil"],
  ["2", "Trabalhista"], ["2", "Consumidor"], ["1", "Anticorrupção"], ["1", "Internet"],
];

const GOVERNANCA = [
  {
    icone: Lock,
    titulo: "Sigilo por cliente",
    texto: "Cada contrato pertence a um cliente, e só o abre quem foi designado a ele. Quem não foi nem descobre que o cliente existe.",
  },
  {
    icone: History,
    titulo: "Registro de acesso",
    texto: "Quem leu, baixou ou exportou, e quando. O registro permanece mesmo depois que o documento é apagado, que é quando a auditoria mais precisa dele.",
  },
  {
    icone: Archive,
    titulo: "Prazo de guarda",
    texto: "Definido por cliente. Vencido o prazo, o documento entra numa fila de revisão. Nada é apagado sem alguém confirmar.",
  },
];

const LIMITES = [
  ["Não emite parecer nem decide", "Ele aponta e mostra onde conferir. A leitura jurídica continua sendo sua, e a responsabilidade também."],
  ["Não substitui ler o contrato", "Ele dirige a leitura: você chega na cláusula sabendo o que procurar e em que página."],
  ["Pode errar, e avisa quando pode", "Alerta cujo trecho não foi localizado vem marcado. É o sinal de conferir aquele antes dos outros."],
  ["Não cobre jurisprudência", "A base é de legislação. Precedente e doutrina continuam com você."],
];

// ─── Peças de composição ─────────────────────────────────────────────────────

const Eyebrow = ({ children, claro = false }) => (
  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.16em", textTransform: "uppercase", color: claro ? "#a5b4fc" : "#6366f1", marginBottom: 14, fontFamily: F }}>
    {children}
  </div>
);

const Titulo = ({ children, claro = false, style }) => (
  <h2 style={{ fontSize: "clamp(26px, 4.2vw, 38px)", fontWeight: 800, color: claro ? "white" : "#0f172a", letterSpacing: "-1.1px", lineHeight: 1.14, margin: "0 0 16px", maxWidth: 640, fontFamily: F, textWrap: "balance", ...style }}>
    {children}
  </h2>
);

const Texto = ({ children, claro = false, style }) => (
  <p style={{ fontSize: 15.5, lineHeight: 1.7, color: claro ? "#cbd5e1" : "#475569", margin: 0, maxWidth: 640, fontFamily: F, ...style }}>
    {children}
  </p>
);

const Selo = ({ children }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10.5, fontWeight: 700, color: "#15803d", background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "3px 10px", borderRadius: 20, fontFamily: F, whiteSpace: "nowrap" }}>
    <CheckCircle size={11} /> {children}
  </span>
);

const BotaoPrimario = ({ onClick, children, grande = false }) => (
  <button onClick={onClick} className="lp-cta" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, padding: grande ? "15px 28px" : "12px 22px", borderRadius: 12, border: "none", cursor: "pointer", background: GRAD, color: "white", fontSize: grande ? 15 : 13.5, fontWeight: 700, fontFamily: F, boxShadow: "0 4px 22px rgba(99,102,241,0.35)", transition: "transform 0.18s, box-shadow 0.18s" }}>
    {children} <ArrowRight size={grande ? 17 : 15} />
  </button>
);

/**
 * O artefato do produto, renderizado de verdade na página.
 *
 * É um alerta real de uma análise real (o contrato de locação dos testes), com
 * os selos que o sistema produz. Mostrar o resultado vale mais do que qualquer
 * parágrafo sobre ele: quem revisa contrato reconhece na hora o que está vendo.
 */
const CartaoDeAlerta = () => (
  <div className="lp-mock" style={{ background: "white", borderRadius: 18, border: "1px solid #e2e8f0", boxShadow: "0 24px 70px rgba(15,23,42,0.14)", overflow: "hidden", fontFamily: F }}>
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "13px 18px", borderBottom: "1px solid #f1f5f9", background: "#f8fafc" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <FileSearch size={14} color="#6366f1" style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 600, color: "#334155", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>contrato-locacao-comercial.pdf</span>
      </div>
      <span style={{ fontSize: 10.5, fontWeight: 800, color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca", padding: "3px 10px", borderRadius: 20, flexShrink: 0 }}>RISCO 78</span>
    </div>

    <div style={{ padding: "18px 20px 20px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: "#dc2626", background: "#fef2f2", padding: "3px 9px", borderRadius: 20, textTransform: "uppercase", letterSpacing: "0.04em" }}>Severidade alta</span>
        <span style={{ fontSize: 10, fontWeight: 700, color: "#6366f1", background: "#eef2ff", padding: "3px 9px", borderRadius: 20, textTransform: "uppercase", letterSpacing: "0.04em" }}>Locação</span>
      </div>

      <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", marginBottom: 10, letterSpacing: "-0.2px" }}>
        Renúncia à ação renovatória
      </div>

      <p style={{ fontSize: 12.5, lineHeight: 1.6, color: "#475569", background: "#f8fafc", borderLeft: "2px solid #e2e8f0", borderRadius: "0 8px 8px 0", padding: "9px 12px", margin: "0 0 12px", fontStyle: "italic" }}>
        "A LOCATÁRIA declara, desde já, renunciar expressa e irrevogavelmente ao
        direito de renovação compulsória da locação"
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
        <Selo>Trecho conferido, pág. 1</Selo>
        <Selo>Artigo conferido na base</Selo>
      </div>

      <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
        <div style={{ fontSize: 10.5, fontWeight: 800, color: "#0f172a", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
          Art. 51, Lei 8.245/1991
        </div>
        <p style={{ fontSize: 12, lineHeight: 1.6, color: "#64748b", margin: 0 }}>
          Nas locações de imóveis destinados ao comércio, o locatário terá direito
          a renovação do contrato, por igual prazo, desde que preenchidos os
          requisitos legais.
        </p>
      </div>
    </div>

    <div style={{ padding: "10px 20px", borderTop: "1px solid #f1f5f9", background: "#fafbfc", fontSize: 11, color: "#94a3b8" }}>
      1 de 14 apontamentos · relatório completo em PDF
    </div>
  </div>
);

// ─── Página ──────────────────────────────────────────────────────────────────

export default function LandingPage({ onEntrar, onCriarConta }) {
  return (
    <div style={{ background: "white", fontFamily: F, color: "#0f172a", minHeight: "100vh" }}>
      <style>{`
        .lp-wrap { max-width: 1120px; margin: 0 auto; padding: 0 clamp(20px, 5vw, 36px); }
        .lp-sec { padding: clamp(56px, 9vw, 104px) 0; }

        .lp-hero { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr); gap: clamp(32px, 5vw, 64px); align-items: center; }
        .lp-num { display: grid; grid-template-columns: repeat(3, auto); gap: clamp(18px, 3vw, 40px); justify-content: start; }
        .lp-versus { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: stretch; }
        .lp-passos { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
        .lp-gov { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .lp-limites { display: grid; grid-template-columns: 1fr 1fr; gap: 18px 30px; }
        .lp-cta-linha { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }

        @media (max-width: 960px) {
          .lp-hero { grid-template-columns: 1fr; }
          .lp-mock { max-width: 480px; }
          .lp-versus, .lp-gov, .lp-limites { grid-template-columns: 1fr; }
          .lp-passos { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 560px) {
          .lp-passos { grid-template-columns: 1fr; }
          .lp-num { grid-template-columns: 1fr; gap: 14px; }
          .lp-cta-linha > button { width: 100%; }
        }

        .lp-cta:hover { transform: translateY(-1px); box-shadow: 0 8px 30px rgba(99,102,241,0.45); }
        .lp-ghost:hover { background: #f1f5f9; }
        .lp-ghost-dark:hover { background: rgba(255,255,255,0.06); }

        @media (prefers-reduced-motion: no-preference) {
          .lp-rise { animation: lpRise 0.6s ease both; }
          .lp-rise-2 { animation: lpRise 0.6s ease 0.12s both; }
          .lp-rise-3 { animation: lpRise 0.7s ease 0.22s both; }
          @keyframes lpRise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        }
      `}</style>

      {/* ── Navegação ───────────────────────────────────────────────────── */}
      <nav style={{ position: "sticky", top: 0, zIndex: 30, background: "rgba(255,255,255,0.92)", backdropFilter: "blur(12px)", borderBottom: "1px solid #f1f5f9" }}>
        <div className="lp-wrap" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, paddingTop: 13, paddingBottom: 13 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 9, background: GRAD, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Shield size={17} color="white" />
            </div>
            <div>
              <div style={{ fontSize: 15.5, fontWeight: 800, letterSpacing: "-0.4px", lineHeight: 1.1 }}>ComplianceAI</div>
              <div style={{ fontSize: 9.5, color: "#94a3b8", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Auditoria Inteligente</div>
            </div>
          </div>
          <button onClick={onEntrar} className="lp-ghost" style={{ padding: "9px 16px", borderRadius: 10, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#334155", fontFamily: F, transition: "background 0.15s" }}>
            Entrar
          </button>
        </div>
      </nav>

      {/* ── Herói ───────────────────────────────────────────────────────── */}
      <header className="lp-sec" style={{ paddingBottom: "clamp(48px, 7vw, 80px)", background: "radial-gradient(900px 420px at 85% -10%, rgba(99,102,241,0.08), transparent), radial-gradient(700px 380px at -10% 30%, rgba(139,92,246,0.06), transparent)" }}>
        <div className="lp-wrap lp-hero">
          <div>
            <div className="lp-rise" style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "6px 14px", borderRadius: 20, background: "#eef2ff", border: "1px solid #e0e7ff", marginBottom: 24 }}>
              <Scale size={13} color="#6366f1" />
              <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5", fontFamily: F }}>Conformidade contratual sob a legislação brasileira</span>
            </div>

            <h1 className="lp-rise" style={{ fontSize: "clamp(34px, 5.8vw, 58px)", fontWeight: 800, letterSpacing: "-2px", lineHeight: 1.05, margin: "0 0 20px", textWrap: "balance", fontFamily: F }}>
              Revisão de contrato com IA que mostra{" "}
              <span style={{ background: GRAD, WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>onde conferir</span>.
            </h1>

            <div className="lp-rise-2">
              <Texto style={{ fontSize: "clamp(15px, 2.2vw, 17px)", marginBottom: 30 }}>
                Envie o contrato e receba, em minutos, as cláusulas problemáticas:
                cada alerta aponta o trecho exato, a página em que ele está e o
                artigo de lei que o sustenta. E o sistema confere tudo isso sozinho
                antes de mostrar, para você saber o que já está confirmado e o que
                merece a sua leitura primeiro.
              </Texto>

              <div className="lp-cta-linha" style={{ marginBottom: 40 }}>
                <BotaoPrimario onClick={onCriarConta} grande>Analisar um contrato</BotaoPrimario>
                <button onClick={onEntrar} className="lp-ghost" style={{ padding: "14px 24px", borderRadius: 12, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 14.5, fontWeight: 600, color: "#334155", fontFamily: F, transition: "background 0.15s" }}>
                  Já tenho conta
                </button>
              </div>
            </div>

            <div className="lp-num lp-rise-3">
              {NUMEROS.map((n) => {
                const Icone = n.icone;
                return (
                  <div key={n.rotulo} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
                      <Icone size={14} color="#6366f1" />
                    </div>
                    <div>
                      <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.6px", lineHeight: 1.1, fontFamily: F }}>{n.valor}</div>
                      <div style={{ fontSize: 11.5, color: "#64748b", lineHeight: 1.35, maxWidth: 130, fontFamily: F }}>{n.rotulo}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="lp-rise-3">
            <CartaoDeAlerta />
            <p style={{ fontSize: 11.5, color: "#94a3b8", margin: "14px 4px 0", fontFamily: F, lineHeight: 1.5 }}>
              Alerta real de uma análise. Os selos verdes são o sistema conferindo,
              em código, o que a IA afirmou.
            </p>
          </div>
        </div>
      </header>

      {/* ── O problema ──────────────────────────────────────────────────── */}
      <section className="lp-sec" style={{ background: "#f8fafc" }}>
        <div className="lp-wrap">
          <Eyebrow>O problema</Eyebrow>
          <Titulo>A parte cara da revisão não é ler. É não deixar passar.</Titulo>
          <Texto>
            Um contrato de vinte páginas tem uma dúzia de armadilhas conhecidas:
            foro eleito em comarca distante, multa sem proporcionalidade, renúncia
            a direito que não se renuncia, dados pessoais sem finalidade definida,
            garantia cumulada onde a lei permite uma só.
          </Texto>
          <Texto style={{ marginTop: 14 }}>
            São sempre as mesmas, e é justamente por isso que escapam. Depois do
            quinto contrato da semana a leitura vira varredura, e o custo de cada
            erro não é seu. É do cliente.
          </Texto>
        </div>
      </section>

      {/* ── A objeção ───────────────────────────────────────────────────── */}
      <section className="lp-sec">
        <div className="lp-wrap">
          <Eyebrow>O diferencial</Eyebrow>
          <Titulo>Por que não jogar o contrato no ChatGPT?</Titulo>
          <Texto style={{ marginBottom: 34 }}>
            Porque uma IA de uso geral responde com a mesma confiança quando acerta
            e quando inventa. Ela parafraseia uma cláusula que não está ali, cita
            um artigo que não existe, e você só descobre conferindo tudo de novo,
            que era exatamente o trabalho que você queria evitar.
          </Texto>

          <div className="lp-versus">
            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 16, padding: "22px 24px" }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "#94a3b8", paddingBottom: 13, marginBottom: 15, borderBottom: "1px solid #e2e8f0", fontFamily: F }}>
                IA de uso geral
              </div>
              <p style={{ fontSize: 14.5, lineHeight: 1.65, color: "#64748b", fontStyle: "italic", margin: "0 0 18px", fontFamily: F }}>
                "A cláusula sexta pode violar a legislação de locações. Recomenda-se
                a adequação dos termos contratuais conforme a Lei nº 8.245/1991."
              </p>
              {[
                "Não diz onde está no contrato",
                "Não aponta o dispositivo específico",
                "Não dá para saber se leu ou supôs",
                "O contrato do seu cliente ficou no histórico de uma conta pessoal",
              ].map(t => (
                <div key={t} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "6px 0" }}>
                  <span style={{ width: 6, height: 2, background: "#cbd5e1", marginTop: 10, flexShrink: 0, borderRadius: 1 }} />
                  <span style={{ fontSize: 13.5, color: "#64748b", lineHeight: 1.5, fontFamily: F }}>{t}</span>
                </div>
              ))}
            </div>

            <div style={{ background: "white", border: "1px solid #c7d2fe", borderRadius: 16, padding: "22px 24px", boxShadow: "0 8px 32px rgba(99,102,241,0.08)", position: "relative", overflow: "hidden" }}>
              <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: GRAD }} />
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "#6366f1", paddingBottom: 13, marginBottom: 15, borderBottom: "1px solid #f1f5f9", fontFamily: F }}>
                O mesmo alerta no ComplianceAI
              </div>
              {[
                ["Aponta a página", "O trecho citado foi localizado no seu PDF: pág. 1."],
                ["Cita o dispositivo, com o texto", "Art. 51, Lei 8.245/1991, anexado ao alerta para você ler ali mesmo."],
                ["Conferido por código, não por confiança", "O sistema procura o trecho no documento e o artigo numa base com dez leis na íntegra."],
                ["Admite o que não conferiu", "Quando algo não confere, o alerta vem marcado. É por ele que você começa."],
              ].map(([t, d]) => (
                <div key={t} style={{ display: "flex", gap: 11, alignItems: "flex-start", padding: "8px 0" }}>
                  <CheckCircle size={15} color="#15803d" style={{ flexShrink: 0, marginTop: 2.5 }} />
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a", lineHeight: 1.4, fontFamily: F }}>{t}</div>
                    <div style={{ fontSize: 12.5, color: "#64748b", lineHeight: 1.55, marginTop: 2, fontFamily: F }}>{d}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Texto style={{ marginTop: 26, fontSize: 14, color: "#64748b" }}>
            A diferença não está no texto do alerta. Está em ele se deixar conferir:
            quando o sistema não localiza o que a IA afirmou, ele diz isso na tela,
            em vez de deixar você descobrir na frente do cliente.
          </Texto>
        </div>
      </section>

      {/* ── Como funciona ───────────────────────────────────────────────── */}
      <section className="lp-sec" style={{ background: "#f8fafc" }}>
        <div className="lp-wrap">
          <Eyebrow>Como funciona</Eyebrow>
          <Titulo>Do upload ao relatório, em quatro passos.</Titulo>
          <div className="lp-passos" style={{ marginTop: 34 }}>
            {PASSOS.map((p, i) => (
              <div key={p.titulo} style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 14, padding: "20px 20px 22px" }}>
                <div style={{ fontSize: 30, fontWeight: 800, color: "#e0e7ff", lineHeight: 1, marginBottom: 12, fontFamily: F }}>
                  {i + 1}
                </div>
                <div style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", marginBottom: 6, lineHeight: 1.3, fontFamily: F }}>{p.titulo}</div>
                <div style={{ fontSize: 13, lineHeight: 1.6, color: "#64748b", fontFamily: F }}>{p.texto}</div>
              </div>
            ))}
          </div>
          <Texto style={{ marginTop: 26, fontSize: 14 }}>
            O resultado sai na tela e em PDF, com os mesmos selos de verificação.
            Na tela, cada revisor marca os alertas como a corrigir, não se aplica
            ou resolvido, e o relatório sai com a marcação de quem o exporta.
          </Texto>
        </div>
      </section>

      {/* ── O que ele verifica ──────────────────────────────────────────── */}
      <section className="lp-sec">
        <div className="lp-wrap">
          <Eyebrow>O que ele verifica</Eyebrow>
          <Titulo>Vinte e nove verificações, organizadas por área do direito.</Titulo>
          <Texto>
            As que valem para qualquer contrato vêm ligadas. As de área específica
            ficam desligadas até você precisar, porque regra de locação em contrato
            de tecnologia só produz alarme falso. Uma área inteira liga em um
            clique quando o contrato é daquele tipo.
          </Texto>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 26 }}>
            {AREAS.map(([n, nome]) => (
              <span key={nome} style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: "#334155", border: "1px solid #e2e8f0", borderRadius: 10, padding: "8px 14px", background: "white", fontWeight: 500, fontFamily: F }}>
                <b style={{ fontSize: 12, fontWeight: 800, color: "#6366f1" }}>{n}</b> {nome}
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginTop: 26, padding: "18px 20px", background: "#eef2ff", borderRadius: 14, border: "1px solid #e0e7ff" }}>
            <FileSearch size={18} color="#6366f1" style={{ flexShrink: 0, marginTop: 2 }} />
            <Texto style={{ fontSize: 14, color: "#3730a3" }}>
              E as regras do seu escritório entram no jogo: prazo máximo de
              pagamento, foro obrigatório, teto de multa. Vira uma regra uma vez e
              passa a ser verificado em todo contrato, sem ninguém precisar lembrar.
            </Texto>
          </div>
        </div>
      </section>

      {/* ── Escritório ──────────────────────────────────────────────────── */}
      <section className="lp-sec" style={{ background: "#f8fafc" }}>
        <div className="lp-wrap">
          <Eyebrow>Feito para escritórios</Eyebrow>
          <Titulo>O contrato do seu cliente não circula pelo escritório inteiro.</Titulo>
          <Texto>
            O texto é processado por um modelo de IA operado por terceiro, aqui e
            em qualquer ferramenta do gênero. A diferença está no que existe em
            volta: quem pode abrir, o que fica registrado e por quanto tempo se
            guarda. É o que um escritório precisa demonstrar numa auditoria.
          </Texto>
          <div className="lp-gov" style={{ marginTop: 32 }}>
            {GOVERNANCA.map((item) => {
              const Icone = item.icone;
              return (
                <div key={item.titulo} style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 14, padding: "22px 22px 24px" }}>
                  <div style={{ width: 38, height: 38, borderRadius: 11, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14 }}>
                    <Icone size={18} color="#6366f1" />
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", marginBottom: 7, fontFamily: F }}>{item.titulo}</div>
                  <div style={{ fontSize: 13, lineHeight: 1.65, color: "#64748b", fontFamily: F }}>{item.texto}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Honestidade ─────────────────────────────────────────────────── */}
      <section className="lp-sec">
        <div className="lp-wrap">
          <Eyebrow>Para ser justo</Eyebrow>
          <Titulo>O que ele não faz.</Titulo>
          <Texto style={{ marginBottom: 30 }}>
            Dizemos antes porque ferramenta que promete demais é desmascarada no
            primeiro contrato difícil, e a confiança que sustenta os selos verdes
            é a mesma que se perderia ali.
          </Texto>
          <div className="lp-limites">
            {LIMITES.map(([titulo, texto]) => (
              <div key={titulo} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                <AlertTriangle size={16} color="#94a3b8" style={{ flexShrink: 0, marginTop: 3 }} />
                <div>
                  <div style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", marginBottom: 4, fontFamily: F }}>{titulo}</div>
                  <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "#64748b", fontFamily: F }}>{texto}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Fecho ───────────────────────────────────────────────────────── */}
      <section className="lp-sec" style={{ background: DARK, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(700px 380px at 20% 0%, rgba(99,102,241,0.16), transparent), radial-gradient(600px 340px at 90% 100%, rgba(139,92,246,0.12), transparent)", pointerEvents: "none" }} />
        <div className="lp-wrap" style={{ position: "relative" }}>
          <Eyebrow claro>Comece agora</Eyebrow>
          <Titulo claro style={{ maxWidth: 560 }}>
            Teste com um contrato que você já revisou.
          </Titulo>
          <Texto claro style={{ maxWidth: 600, marginBottom: 34 }}>
            É a forma mais rápida de julgar a ferramenta: passe por ela um contrato
            cujo resultado você conhece e compare com o que tinha anotado. O que
            ela pegou, o que deixou passar e o que apontou a mais.
          </Texto>
          <div className="lp-cta-linha">
            <BotaoPrimario onClick={onCriarConta} grande>Criar conta e analisar</BotaoPrimario>
            <button onClick={onEntrar} className="lp-ghost-dark" style={{ padding: "14px 24px", borderRadius: 12, border: "1px solid #2a3247", background: "transparent", cursor: "pointer", fontSize: 14.5, fontWeight: 600, color: "#e2e8f0", fontFamily: F, transition: "background 0.15s" }}>
              Entrar
            </button>
          </div>
        </div>
      </section>

      <footer style={{ background: DARK, borderTop: "1px solid #1a2032", padding: "24px 0 32px" }}>
        <div className="lp-wrap" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ width: 24, height: 24, borderRadius: 7, background: GRAD, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Shield size={13} color="white" />
            </div>
            <span style={{ fontSize: 12.5, color: "#64748b", fontFamily: F }}>ComplianceAI · Recife, PE</span>
          </div>
          <span style={{ fontSize: 12.5, color: "#64748b", fontFamily: F }}>Análise de conformidade contratual com IA</span>
        </div>
      </footer>
    </div>
  );
}
