/**
 * Pagina publica do ComplianceAI.
 *
 * Antes, abrir o site caia direto num formulario de senha, o que so faz sentido
 * para quem ja conhece a ferramenta. Quem chega por indicacao precisa entender o
 * que ela faz e, principalmente, por que nao basta colar o contrato numa IA de
 * uso geral: essa e a objecao que decide a conversa com um advogado.
 *
 * O visual segue a identidade do app, para a transicao ao clicar em Entrar nao
 * parecer outro produto.
 */
import {
  Shield, FileSearch, Scale, Lock, History, Archive,
  CheckCircle, ArrowRight, AlertTriangle, Briefcase,
} from "lucide-react";

const F = "'DM Sans', sans-serif";

const PASSOS = [
  {
    titulo: "Você envia o contrato",
    texto: "PDF ou DOCX, pelo navegador. Se for digitalizado, o sistema faz a leitura óptica.",
  },
  {
    titulo: "O sistema busca a lei aplicável",
    texto: "Busca por semelhança de sentido em 3.927 artigos de dez leis brasileiras completas, e não na memória do modelo.",
  },
  {
    titulo: "A IA analisa contra as suas regras",
    texto: "As 29 verificações padrão mais as que o seu escritório definir.",
  },
  {
    titulo: "Cada alerta é conferido antes de aparecer",
    texto: "Trecho localizado no contrato, com a página. Artigo localizado na base legal. O que não confere vem marcado.",
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
    titulo: "Acesso por cliente",
    texto: "Cada documento pertence a um cliente, e só enxerga quem foi designado a ele. Quem não foi não vê o contrato nem descobre que ele existe.",
  },
  {
    icone: History,
    titulo: "Registro de acesso",
    texto: "Quem abriu, baixou ou exportou, e quando. O registro permanece mesmo depois que o documento é apagado.",
  },
  {
    icone: Archive,
    titulo: "Prazo de guarda",
    texto: "Definido por cliente. Vencido o prazo, o documento entra em uma fila para revisão. Nada é apagado sem alguém confirmar.",
  },
];

const LIMITES = [
  ["Não emite parecer nem decide", "Ele aponta e mostra onde conferir. A leitura jurídica continua sendo sua, e a responsabilidade também."],
  ["Não substitui ler o contrato", "Ele torna a leitura dirigida: você chega no ponto sabendo o que procurar e em que página."],
  ["Pode errar, e avisa quando pode", "Alerta cujo trecho não foi localizado no documento vem marcado. É o sinal de conferir aquele antes dos outros."],
  ["Não cobre jurisprudência", "A base é de legislação. Precedente e doutrina continuam com você."],
];

const Secao = ({ children, fundo = "transparent", style }) => (
  <section style={{ background: fundo, padding: "clamp(48px, 8vw, 88px) 0", ...style }}>
    <div className="lp-wrap" style={{ maxWidth: 1080, margin: "0 auto", padding: "0 clamp(18px, 5vw, 32px)" }}>
      {children}
    </div>
  </section>
);

const Eyebrow = ({ children }) => (
  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6366f1", marginBottom: 14, fontFamily: F }}>
    {children}
  </div>
);

const Titulo = ({ children, style }) => (
  <h2 style={{ fontSize: "clamp(24px, 4vw, 34px)", fontWeight: 800, color: "#0f172a", letterSpacing: "-0.9px", lineHeight: 1.18, margin: "0 0 14px", maxWidth: 620, fontFamily: F, textWrap: "balance", ...style }}>
    {children}
  </h2>
);

const Texto = ({ children, style }) => (
  <p style={{ fontSize: 15, lineHeight: 1.68, color: "#475569", margin: 0, maxWidth: 620, fontFamily: F, ...style }}>
    {children}
  </p>
);

export default function LandingPage({ onEntrar, onCriarConta }) {
  return (
    <div style={{ background: "white", fontFamily: F, color: "#0f172a", minHeight: "100vh" }}>
      <style>{`
        .lp-versus { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .lp-passos { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
        .lp-gov { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .lp-limites { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 26px; }
        .lp-hero-cta { display: flex; gap: 10px; flex-wrap: wrap; }
        @media (max-width: 900px) {
          .lp-versus, .lp-gov, .lp-limites { grid-template-columns: 1fr !important; }
          .lp-passos { grid-template-columns: 1fr 1fr !important; }
        }
        @media (max-width: 560px) {
          .lp-passos { grid-template-columns: 1fr !important; }
          .lp-hero-cta > button { width: 100%; justify-content: center; }
        }
        .lp-btn-primary:hover { transform: translateY(-1px); box-shadow: 0 8px 26px rgba(99,102,241,0.34); }
        .lp-btn-ghost:hover { background: #f1f5f9; }
      `}</style>

      {/* ── Topo ─────────────────────────────────────────────────────────── */}
      <nav style={{ position: "sticky", top: 0, zIndex: 20, background: "rgba(255,255,255,0.92)", backdropFilter: "blur(10px)", borderBottom: "1px solid #f1f5f9" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "13px clamp(18px, 5vw, 32px)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Shield size={16} color="white" />
            </div>
            <span style={{ fontSize: 15.5, fontWeight: 800, letterSpacing: "-0.4px" }}>ComplianceAI</span>
          </div>
          <button onClick={onEntrar} className="lp-btn-ghost" style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#334155", fontFamily: F, transition: "background 0.15s" }}>
            Entrar
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <Secao style={{ paddingTop: "clamp(52px, 9vw, 96px)", paddingBottom: "clamp(40px, 6vw, 64px)" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "5px 13px", borderRadius: 20, background: "#eef2ff", marginBottom: 22 }}>
          <Scale size={13} color="#6366f1" />
          <span style={{ fontSize: 12, fontWeight: 600, color: "#6366f1" }}>3.927 artigos de lei indexados, dez leis na íntegra</span>
        </div>
        <h1 style={{ fontSize: "clamp(32px, 6.2vw, 56px)", fontWeight: 800, letterSpacing: "-1.8px", lineHeight: 1.06, margin: "0 0 18px", maxWidth: 780, textWrap: "balance" }}>
          Revisão de contrato com IA que mostra{" "}
          <span style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>onde conferir</span>.
        </h1>
        <Texto style={{ fontSize: "clamp(15px, 2.2vw, 17.5px)", maxWidth: 660, marginBottom: 30 }}>
          Você envia o contrato. Em minutos recebe um relatório com as cláusulas problemáticas,
          cada uma apontando o trecho exato, a página em que ele está e o artigo de lei que a
          sustenta. E dizendo, alerta por alerta, o que foi possível conferir automaticamente
          e o que você precisa checar na fonte.
        </Texto>
        <div className="lp-hero-cta">
          <button onClick={onCriarConta} className="lp-btn-primary" style={{ display: "flex", alignItems: "center", gap: 8, padding: "13px 24px", borderRadius: 11, border: "none", cursor: "pointer", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontSize: 14.5, fontWeight: 700, fontFamily: F, boxShadow: "0 4px 20px rgba(99,102,241,0.3)", transition: "all 0.2s" }}>
            Analisar um contrato <ArrowRight size={16} />
          </button>
          <button onClick={onEntrar} className="lp-btn-ghost" style={{ display: "flex", alignItems: "center", gap: 7, padding: "13px 22px", borderRadius: 11, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 14.5, fontWeight: 600, color: "#334155", fontFamily: F, transition: "background 0.15s" }}>
            Já tenho conta
          </button>
        </div>
      </Secao>

      {/* ── O problema ───────────────────────────────────────────────────── */}
      <Secao fundo="#f8fafc">
        <Eyebrow>O problema</Eyebrow>
        <Titulo>A parte cara da revisão não é ler. É não deixar passar.</Titulo>
        <Texto>
          Um contrato de vinte páginas tem uma dúzia de armadilhas conhecidas: foro eleito em
          comarca distante, multa sem proporcionalidade, renúncia a direito que não se renuncia,
          tratamento de dados sem finalidade definida, garantia cumulada onde a lei permite uma só.
        </Texto>
        <Texto style={{ marginTop: 14 }}>
          São sempre as mesmas, e é por isso que escapam. Depois do quinto contrato da semana,
          a leitura vira varredura, e a varredura tem um custo por erro que não é seu. É do cliente.
        </Texto>
      </Secao>

      {/* ── A objeção ────────────────────────────────────────────────────── */}
      <Secao>
        <Eyebrow>A objeção</Eyebrow>
        <Titulo>Por que não jogar o contrato no ChatGPT?</Titulo>
        <Texto style={{ marginBottom: 30 }}>
          Porque uma IA de uso geral responde com confiança mesmo sem ter como sustentar a
          resposta. Ela parafraseia uma cláusula que não está ali, cita um artigo que não existe,
          e apresenta as duas coisas com a mesma segurança de quando acerta. Para quem revisa,
          isso é pior do que não ter resposta: obriga a conferir tudo de novo.
        </Texto>

        <div className="lp-versus">
          <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 14, padding: "20px 22px 22px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#94a3b8", paddingBottom: 12, marginBottom: 14, borderBottom: "1px solid #f1f5f9" }}>
              IA de uso geral
            </div>
            <p style={{ fontSize: 14.5, lineHeight: 1.6, color: "#64748b", fontStyle: "italic", margin: "0 0 16px" }}>
              “A cláusula sexta pode violar a LGPD. Recomenda-se adequação da política de
              tratamento de dados conforme a Lei nº 13.709/2018.”
            </p>
            {["Não diz onde está no contrato", "Não aponta o dispositivo específico", "Não dá para saber se leu ou supôs", "O contrato do seu cliente saiu do escritório"].map(t => (
              <div key={t} style={{ display: "flex", gap: 9, alignItems: "flex-start", padding: "5px 0" }}>
                <span style={{ width: 5, height: 1.5, background: "#cbd5e1", marginTop: 11, flexShrink: 0 }} />
                <span style={{ fontSize: 13.5, color: "#64748b", lineHeight: 1.5 }}>{t}</span>
              </div>
            ))}
          </div>

          <div style={{ background: "white", border: "1px solid #c7d2fe", borderLeft: "3px solid #6366f1", borderRadius: 14, padding: "20px 22px 22px", boxShadow: "0 4px 24px rgba(99,102,241,0.07)" }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#6366f1", paddingBottom: 12, marginBottom: 14, borderBottom: "1px solid #f1f5f9" }}>
              ComplianceAI
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 11 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "#dc2626", background: "#fef2f2", padding: "3px 9px", borderRadius: 20, textTransform: "uppercase", letterSpacing: "0.04em" }}>Severidade alta</span>
              <span style={{ fontSize: 10, fontWeight: 700, color: "#6366f1", background: "#eef2ff", padding: "3px 9px", borderRadius: 20, textTransform: "uppercase", letterSpacing: "0.04em" }}>Proteção de dados</span>
            </div>
            <div style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", marginBottom: 10 }}>
              Finalidade indeterminada no tratamento de dados
            </div>
            <p style={{ fontSize: 13.5, lineHeight: 1.6, color: "#475569", background: "#f8fafc", borderRadius: 8, padding: "10px 12px", margin: "0 0 10px", fontStyle: "italic" }}>
              “…autorizando a LOCADORA a utilizá-los para qualquer finalidade, inclusive análise
              de crédito por terceiros e compartilhamento com empresas do grupo, sem necessidade
              de comunicação aos titulares.”
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 13 }}>
              {["Trecho conferido, pág. 2", "Artigo conferido na base"].map(t => (
                <span key={t} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10.5, fontWeight: 700, color: "#15803d", background: "#f0fdf4", padding: "3px 9px", borderRadius: 20 }}>
                  <CheckCircle size={11} /> {t}
                </span>
              ))}
            </div>
            <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#0f172a", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 5 }}>
                Art. 6º, I, Lei 13.709/2018
              </div>
              <p style={{ fontSize: 13, lineHeight: 1.55, color: "#64748b", margin: 0 }}>
                Realização do tratamento para propósitos legítimos, específicos, explícitos e
                informados ao titular, sem possibilidade de tratamento posterior de forma
                incompatível com essas finalidades.
              </p>
            </div>
          </div>
        </div>

        <Texto style={{ marginTop: 24, fontSize: 14, color: "#64748b" }}>
          A diferença não está no texto do alerta. Está nos dois selos verdes: o sistema procurou
          o trecho dentro do seu PDF e achou na página 2, e procurou o artigo citado entre 3.927
          artigos de dez leis na íntegra e achou. Quando não acha, ele diz que não achou, em vez de
          deixar você descobrir depois.
        </Texto>
      </Secao>

      {/* ── Como funciona ────────────────────────────────────────────────── */}
      <Secao fundo="#f8fafc">
        <Eyebrow>Como funciona</Eyebrow>
        <Titulo>Quatro passos, sem instalação.</Titulo>
        <div className="lp-passos" style={{ marginTop: 30 }}>
          {PASSOS.map((p, i) => (
            <div key={p.titulo} style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 13, padding: "18px 18px 20px" }}>
              <div style={{ width: 26, height: 26, borderRadius: 7, background: "#eef2ff", color: "#6366f1", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, marginBottom: 12 }}>
                {i + 1}
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", marginBottom: 6, lineHeight: 1.3 }}>{p.titulo}</div>
              <div style={{ fontSize: 13, lineHeight: 1.55, color: "#64748b" }}>{p.texto}</div>
            </div>
          ))}
        </div>
        <Texto style={{ marginTop: 24, fontSize: 14 }}>
          O resultado sai na tela e em PDF. Na tela, você marca cada ponto como a corrigir,
          não se aplica ou resolvido, e cada revisor tem a própria marcação.
        </Texto>
      </Secao>

      {/* ── Verificações ─────────────────────────────────────────────────── */}
      <Secao>
        <Eyebrow>O que ele verifica</Eyebrow>
        <Titulo>Vinte e nove verificações, organizadas por área.</Titulo>
        <Texto>
          As que valem para qualquer contrato vêm ligadas. As de área específica ficam desligadas
          até você precisar delas, porque regra de locação em contrato de tecnologia só produz
          alarme falso. Liga a área inteira em um clique quando for revisar um contrato daquele tipo.
        </Texto>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 22 }}>
          {AREAS.map(([n, nome]) => (
            <span key={nome} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, color: "#475569", border: "1px solid #e2e8f0", borderRadius: 9, padding: "7px 13px", background: "white" }}>
              <b style={{ fontSize: 12, fontWeight: 800, color: "#6366f1" }}>{n}</b> {nome}
            </span>
          ))}
        </div>
        <div style={{ display: "flex", gap: 11, alignItems: "flex-start", marginTop: 24, padding: "16px 18px", background: "#f8fafc", borderRadius: 12 }}>
          <FileSearch size={17} color="#6366f1" style={{ flexShrink: 0, marginTop: 2 }} />
          <Texto style={{ fontSize: 14 }}>
            E você cria as suas. Se o escritório não aceita prazo de pagamento acima de sessenta
            dias, ou exige foro em Recife, isso vira uma regra e passa a ser verificado em todo
            contrato, sem ninguém precisar lembrar.
          </Texto>
        </div>
      </Secao>

      {/* ── Sigilo ───────────────────────────────────────────────────────── */}
      <Secao fundo="#f8fafc">
        <Eyebrow>Sigilo</Eyebrow>
        <Titulo>O contrato do seu cliente não circula pelo escritório inteiro.</Titulo>
        <Texto>
          O texto do contrato é processado por um modelo de IA operado por terceiro, aqui e em
          qualquer outra ferramenta do gênero. A diferença é o que existe em volta dele:
          quem pode abrir, o que fica registrado e por quanto tempo é guardado.
        </Texto>
        <div className="lp-gov" style={{ marginTop: 28 }}>
          {GOVERNANCA.map((item) => {
            const Icone = item.icone;
            const { titulo, texto } = item;
            return (
            <div key={titulo} style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 13, padding: "20px 20px 22px" }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 13 }}>
                <Icone size={17} color="#6366f1" />
              </div>
              <div style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", marginBottom: 6 }}>{titulo}</div>
              <div style={{ fontSize: 13, lineHeight: 1.6, color: "#64748b" }}>{texto}</div>
            </div>
            );
          })}
        </div>
      </Secao>

      {/* ── Limites ──────────────────────────────────────────────────────── */}
      <Secao>
        <Eyebrow>Honestidade</Eyebrow>
        <Titulo>O que ele não faz.</Titulo>
        <Texto style={{ marginBottom: 26 }}>
          Vale dizer antes, porque ferramenta que promete demais é descoberta no primeiro
          contrato difícil.
        </Texto>
        <div className="lp-limites">
          {LIMITES.map(([titulo, texto]) => (
            <div key={titulo} style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
              <AlertTriangle size={15} color="#94a3b8" style={{ flexShrink: 0, marginTop: 3 }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", marginBottom: 3 }}>{titulo}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "#64748b" }}>{texto}</div>
              </div>
            </div>
          ))}
        </div>
      </Secao>

      {/* ── Fecho ────────────────────────────────────────────────────────── */}
      <Secao fundo="#0f172a" style={{ color: "white" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <Briefcase size={16} color="#a5b4fc" />
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#a5b4fc" }}>Comece agora</span>
        </div>
        <Titulo style={{ color: "white", maxWidth: 560 }}>
          Teste com um contrato que você já revisou.
        </Titulo>
        <Texto style={{ color: "#cbd5e1", maxWidth: 580, marginBottom: 30 }}>
          É a forma mais rápida de avaliar: passe pela ferramenta um contrato cujo resultado você
          já conhece e compare com o que tinha anotado. O que ela pegou, o que deixou passar e o
          que apontou a mais.
        </Texto>
        <div className="lp-hero-cta">
          <button onClick={onCriarConta} className="lp-btn-primary" style={{ display: "flex", alignItems: "center", gap: 8, padding: "13px 24px", borderRadius: 11, border: "none", cursor: "pointer", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontSize: 14.5, fontWeight: 700, fontFamily: F, boxShadow: "0 4px 22px rgba(99,102,241,0.4)", transition: "all 0.2s" }}>
            Criar conta <ArrowRight size={16} />
          </button>
          <button onClick={onEntrar} style={{ padding: "13px 22px", borderRadius: 11, border: "1px solid #334155", background: "transparent", cursor: "pointer", fontSize: 14.5, fontWeight: 600, color: "#e2e8f0", fontFamily: F }}>
            Entrar
          </button>
        </div>
      </Secao>

      <footer style={{ background: "#0f172a", borderTop: "1px solid #1e293b", padding: "22px 0 30px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 clamp(18px, 5vw, 32px)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12.5, color: "#64748b" }}>ComplianceAI · Recife, PE</span>
          <span style={{ fontSize: 12.5, color: "#64748b" }}>Análise de conformidade contratual com IA</span>
        </div>
      </footer>
    </div>
  );
}
