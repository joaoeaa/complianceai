/**
 * Página pública do ComplianceAI, portada do protótipo aprovado
 * (artefato "landing-prototipo", v2-navbar).
 *
 * A tese do produto, "IA que se deixa conferir", vira o próprio herói: um
 * alerta real de análise que se verifica ao vivo, com linha de varredura,
 * selos surgindo e o texto da lei por último. Nenhum movimento da página é
 * decorativo à toa; o único efeito ousado é o que significa alguma coisa.
 *
 * Sobre a implementação: reveal, contagem, spotlight e a sequência do cartão
 * são imperativos dentro de um useEffect, como no protótipo. Isso convive bem
 * com o React porque o reconciliador só reescreve um atributo quando o virtual
 * DOM muda entre renders; classes e textos aplicados por fora sobrevivem aos
 * re-renders do painel de comparação. Todos os efeitos respeitam
 * prefers-reduced-motion.
 *
 * Números do herói medidos no banco de produção em 12/08/2026. Para recontar:
 *   select count(*) from (select distinct d.source, ch.article_ref
 *   from legal_chunks ch join legal_documents d on d.id=ch.document_id
 *   where ch.article_ref is not null) t
 */
import { useState, useEffect, useRef, useCallback } from "react";

const LEIS = [
  ["Código Civil", "Lei 10.406/2002"],
  ["CLT", "Decreto-Lei 5.452/1943"],
  ["CDC", "Lei 8.078/1990"],
  ["LGPD", "Lei 13.709/2018"],
  ["Marco Civil da Internet", "Lei 12.965/2014"],
  ["Lei Anticorrupção", "Lei 12.846/2013"],
  ["Lei de Licitações", "Lei 14.133/2021"],
  ["Lei do Inquilinato", "Lei 8.245/1991"],
  ["Lei das S.A.", "Lei 6.404/1976"],
  ["Propriedade Industrial", "Lei 9.279/1996"],
];

const AREAS = [
  ["5", "Estrutura do contrato"], ["5", "Proteção de dados"], ["5", "Locação"],
  ["3", "Societário"], ["3", "Propriedade industrial"], ["2", "Civil"],
  ["2", "Trabalhista"], ["2", "Consumidor"], ["1", "Anticorrupção"], ["1", "Internet"],
];

const GANHOS = [
  ["Aponta a página", "O trecho citado foi localizado no seu PDF: pág. 1."],
  ["Cita o dispositivo, com o texto", "Art. 51, Lei 8.245/1991, anexado ao alerta para você ler ali mesmo."],
  ["Conferido por código, não por confiança", "O sistema procura o trecho no documento e o artigo numa base com dez leis na íntegra."],
  ["Admite o que não conferiu", "Quando algo não confere, o alerta vem marcado. É por ele que você começa."],
];

const LACUNAS = [
  "Não diz onde está no contrato",
  "Não aponta o dispositivo específico",
  "Não dá para saber se leu ou supôs",
  "O contrato do seu cliente ficou no histórico de uma conta pessoal",
];

const PASSOS = [
  ["Envie o contrato", "PDF ou DOCX, pelo navegador. Documento digitalizado passa por leitura óptica."],
  ["O sistema busca a lei", "Busca semântica em 3.927 artigos de dez leis completas, e não na memória do modelo."],
  ["A IA analisa com as suas regras", "As 29 verificações padrão mais as que o seu escritório definir, por área do direito."],
  ["Cada alerta é conferido", "Trecho localizado no contrato, com a página. Artigo localizado na base. O que não confere vem marcado."],
];

const LIMITES = [
  ["Não emite parecer nem decide", "Ele aponta e mostra onde conferir. A leitura jurídica continua sendo sua, e a responsabilidade também."],
  ["Não substitui ler o contrato", "Ele dirige a leitura: você chega na cláusula sabendo o que procurar e em que página."],
  ["Pode errar, e avisa quando pode", "Alerta cujo trecho não foi localizado vem marcado. É o sinal de conferir aquele antes dos outros."],
  ["Não cobre jurisprudência", "A base é de legislação. Precedente e doutrina continuam com você."],
];

const CSS = `
  .lp-root {
    --paper: #ffffff; --mist: #f6f7fb; --ink: #0b1220; --slate: #55607a;
    --soft: #8a93a8; --line: #e6e9f2; --indigo: #6366f1; --violet: #8b5cf6;
    --deep: #0c0f1a; --deep-line: #1c2436;
    --green-ink: #15803d; --green-bg: #ecfdf5; --green-line: #bbf7d0;
    --red: #dc2626; --red-bg: #fef2f2; --red-line: #fecaca;
    --grad: linear-gradient(135deg, #6366f1, #8b5cf6);
    --sans: 'DM Sans', 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: var(--paper); color: var(--ink); font-family: var(--sans);
    line-height: 1.6; min-height: 100vh;
  }
  .lp-root button { font-family: var(--sans); }
  .lp-root section[id], .lp-root header[id] { scroll-margin-top: 84px; }

  .lp-wrap { max-width: 1140px; margin: 0 auto; padding: 0 clamp(20px, 5vw, 36px); }
  .lp-sec { padding: clamp(60px, 9vw, 108px) 0; }

  .lp-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; color: var(--indigo); margin-bottom: 14px; }
  .lp-eyebrow.claro { color: #a5b4fc; }
  .lp-root h2 { font-size: clamp(26px, 4.2vw, 40px); font-weight: 800; letter-spacing: -1.2px; line-height: 1.12; margin: 0 0 16px; max-width: 660px; text-wrap: balance; }
  .lp-lede { font-size: 15.5px; color: var(--slate); max-width: 640px; margin: 0; }

  .reveal { opacity: 0; transform: translateY(18px); transition: opacity .7s ease, transform .7s ease; }
  .reveal.on { opacity: 1; transform: none; }
  .d1 { transition-delay: .08s; } .d2 { transition-delay: .16s; }
  .d3 { transition-delay: .26s; } .d4 { transition-delay: .38s; }
  @media (prefers-reduced-motion: reduce) {
    .reveal { opacity: 1; transform: none; transition: none; }
  }

  /* ── Navegação em pílula ────────────────────────────────────────────── */
  .lp-nav { position: fixed; top: 14px; left: 0; right: 0; z-index: 40; padding: 0 16px; }
  .lp-nav-in {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    max-width: 780px; margin: 0 auto; padding: 7px 7px 7px 14px;
    background: rgba(15,19,32,.74); border: 1px solid rgba(255,255,255,.1);
    border-radius: 999px; backdrop-filter: blur(16px);
    box-shadow: 0 10px 40px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
  }
  .lp-logo { display: flex; align-items: center; gap: 9px; color: white; text-decoration: none; flex-shrink: 0; background: none; border: none; cursor: pointer; padding: 0; }
  .lp-logo-badge { width: 28px; height: 28px; border-radius: 8px; background: var(--grad); display: grid; place-items: center; box-shadow: 0 4px 14px rgba(99,102,241,.4); }
  .lp-logo b { font-size: 14.5px; font-weight: 800; letter-spacing: -.3px; line-height: 1; }
  .lp-nav-links { display: flex; align-items: center; gap: 4px; }
  .lp-nav-links a {
    padding: 8px 13px; border-radius: 999px; text-decoration: none;
    font-size: 12.5px; font-weight: 600; color: #9aa5c0;
    transition: color .15s, background .15s; white-space: nowrap;
  }
  .lp-nav-links a:hover { color: white; background: rgba(255,255,255,.07); }
  .lp-nav-acoes { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
  .lp-nav-entrar {
    padding: 8px 13px; border-radius: 999px; border: none; background: none; cursor: pointer;
    font-size: 12.5px; font-weight: 600; color: #dde3f0;
    transition: background .15s; white-space: nowrap;
  }
  .lp-nav-entrar:hover { background: rgba(255,255,255,.07); }
  .lp-nav-cta {
    display: inline-flex; align-items: center; gap: 6px; border: none; cursor: pointer;
    padding: 9px 16px; border-radius: 999px;
    background: var(--grad); color: white; font-size: 12.5px; font-weight: 700;
    box-shadow: 0 4px 16px rgba(99,102,241,.4);
    transition: transform .15s, box-shadow .15s; white-space: nowrap;
  }
  .lp-nav-cta:hover { transform: translateY(-1px); box-shadow: 0 6px 22px rgba(99,102,241,.55); }
  @media (max-width: 760px) { .lp-nav-links { display: none; } }
  /* No espaco apertado sai o nome escrito, nunca o Entrar: quem volta pelo
     celular precisa do login na barra, e o escudo sozinho ja marca a marca. */
  @media (max-width: 380px) { .lp-logo b { display: none; } }

  /* ── Botões ─────────────────────────────────────────────────────────── */
  .lp-cta {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 15px 28px; border-radius: 12px; border: none; cursor: pointer;
    background: var(--grad); color: white; font-size: 15px; font-weight: 700;
    box-shadow: 0 6px 26px rgba(99,102,241,.42);
    transition: transform .18s, box-shadow .18s;
    position: relative; overflow: hidden;
  }
  .lp-cta::after {
    content: ""; position: absolute; top: 0; bottom: 0; width: 40%; left: -60%;
    background: linear-gradient(100deg, transparent, rgba(255,255,255,.35), transparent);
    transform: skewX(-18deg);
  }
  .lp-cta:hover { transform: translateY(-1px); box-shadow: 0 10px 34px rgba(99,102,241,.55); }
  @media (prefers-reduced-motion: no-preference) {
    .lp-cta:hover::after { animation: lpBrilho .8s ease; }
  }
  @keyframes lpBrilho { to { left: 130%; } }
  .lp-ghost { padding: 14px 24px; border-radius: 12px; border: 1px solid var(--line); background: white; color: #33405c; font-size: 14.5px; font-weight: 600; cursor: pointer; transition: background .15s; }
  .lp-ghost:hover { background: var(--mist); }
  .lp-ghost.escuro { background: transparent; border-color: rgba(255,255,255,.16); color: #dde3f0; }
  .lp-ghost.escuro:hover { background: rgba(255,255,255,.07); }

  /* ── Herói ──────────────────────────────────────────────────────────── */
  .lp-hero {
    background: var(--deep); color: white; position: relative; overflow: hidden;
    padding: clamp(104px, 13vw, 150px) 0 clamp(56px, 7vw, 88px);
  }
  .lp-hero::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background:
      radial-gradient(760px 400px at 78% -10%, rgba(99,102,241,.22), transparent 65%),
      radial-gradient(600px 380px at 8% 108%, rgba(139,92,246,.14), transparent 65%);
  }
  .lp-hero::after {
    content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .5;
    background-image:
      linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
    background-size: 44px 44px;
    -webkit-mask-image: radial-gradient(800px 500px at 60% 20%, black, transparent 75%);
    mask-image: radial-gradient(800px 500px at 60% 20%, black, transparent 75%);
  }
  .lp-aurora { position: absolute; width: 560px; height: 560px; border-radius: 50%; filter: blur(90px); opacity: .32; pointer-events: none; }
  .lp-aurora-a { background: #6366f1; top: -220px; right: -120px; }
  .lp-aurora-b { background: #8b5cf6; bottom: -260px; left: -140px; opacity: .22; }
  @media (prefers-reduced-motion: no-preference) {
    .lp-aurora-a { animation: lpDerivaA 16s ease-in-out infinite alternate; }
    .lp-aurora-b { animation: lpDerivaB 19s ease-in-out infinite alternate; }
  }
  @keyframes lpDerivaA { to { transform: translate(-70px, 60px) scale(1.12); } }
  @keyframes lpDerivaB { to { transform: translate(80px, -50px) scale(1.08); } }
  .lp-hero .lp-wrap { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(0,1.06fr) minmax(0,.94fr); gap: clamp(34px,5vw,64px); align-items: center; }

  .lp-hero-badge { display: inline-flex; align-items: center; gap: 7px; padding: 6px 14px; border-radius: 20px; background: rgba(99,102,241,.14); border: 1px solid rgba(99,102,241,.32); margin-bottom: 24px; font-size: 12px; font-weight: 600; color: #c7cffc; }
  .lp-hero h1 { font-size: clamp(34px, 5.6vw, 58px); font-weight: 800; letter-spacing: -2px; line-height: 1.05; margin: 0 0 20px; text-wrap: balance; }
  .lp-grad-text { background: linear-gradient(135deg, #a5b4fc, #c4b5fd); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
  .lp-hero .lp-lede { color: #aab3c8; margin-bottom: 30px; font-size: clamp(15px, 2.1vw, 17px); }
  .lp-cta-linha { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 42px; }

  .lp-nums { display: flex; gap: clamp(20px, 3.4vw, 44px); flex-wrap: wrap; }
  .lp-num-v { font-size: 24px; font-weight: 800; letter-spacing: -.6px; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .lp-num-l { font-size: 11.5px; color: #7c86a0; line-height: 1.35; max-width: 130px; }

  /* ── Cartão que se verifica ─────────────────────────────────────────── */
  @property --lpAng { syntax: "<angle>"; initial-value: 0deg; inherits: false; }
  .lp-halo {
    position: relative; border-radius: 20px; padding: 1.5px;
    max-width: 502px; margin-left: auto;
    background: conic-gradient(from var(--lpAng), rgba(99,102,241,.05), rgba(99,102,241,.85) 12%, rgba(139,92,246,.5) 22%, rgba(99,102,241,.05) 38%);
  }
  @media (prefers-reduced-motion: no-preference) {
    .lp-halo { animation: lpGirar 7s linear infinite; }
  }
  @keyframes lpGirar { to { --lpAng: 360deg; } }
  .lp-mock { background: white; color: var(--ink); border-radius: 18.5px; box-shadow: 0 30px 80px rgba(0,0,0,.5); overflow: hidden; }
  .lp-mock-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 13px 18px; border-bottom: 1px solid #f1f3f9; background: #fafbfe; }
  .lp-mock-file { display: flex; align-items: center; gap: 8px; min-width: 0; font-family: var(--mono); font-size: 11.5px; font-weight: 500; color: #44506b; }
  .lp-mock-file span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lp-pill { font-size: 10px; font-weight: 800; padding: 3px 10px; border-radius: 20px; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap; }
  .lp-pill-risco { color: var(--red); background: var(--red-bg); border: 1px solid var(--red-line); }
  .lp-pill-sev { color: var(--red); background: var(--red-bg); }
  .lp-pill-area { color: var(--indigo); background: #eef2ff; }
  .lp-mock-body { padding: 18px 20px 20px; }
  .lp-mock-alert-t { font-size: 15.5px; font-weight: 700; letter-spacing: -.2px; margin: 10px 0; }
  .lp-excerpt {
    position: relative; overflow: hidden;
    font-size: 12.5px; color: #4a5670; background: #f7f8fc;
    border-left: 2px solid var(--line); border-radius: 0 8px 8px 0;
    padding: 9px 12px; margin-bottom: 12px; font-style: italic;
  }
  .lp-scanline {
    position: absolute; top: 0; bottom: 0; width: 46%; left: -50%;
    background: linear-gradient(90deg, transparent, rgba(99,102,241,.14), rgba(139,92,246,.18), transparent);
    opacity: 0;
  }
  .lp-selos { display: flex; flex-wrap: wrap; gap: 6px; min-height: 26px; margin-bottom: 14px; }
  .lp-selo {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 10.5px; font-weight: 700; color: var(--green-ink);
    background: var(--green-bg); border: 1px solid var(--green-line);
    padding: 3px 10px; border-radius: 20px; white-space: nowrap;
    opacity: 0; transform: scale(.72);
  }
  .lp-lei { border-top: 1px solid #f1f3f9; padding-top: 12px; opacity: 0; }
  .lp-lei b { font-size: 10.5px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; display: block; margin-bottom: 4px; }
  .lp-lei p { font-size: 12px; color: #66718c; margin: 0; }
  .lp-mock-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 20px; border-top: 1px solid #f1f3f9; background: #fafbfe; font-size: 11px; color: var(--soft); }
  .lp-status { display: inline-flex; align-items: center; gap: 6px; font-family: var(--mono); font-size: 10.5px; color: var(--soft); }
  .lp-status .lp-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--indigo); }
  .lp-replay { border: none; background: none; color: var(--indigo); font-size: 11px; font-weight: 700; cursor: pointer; padding: 2px 4px; }

  @media (prefers-reduced-motion: no-preference) {
    .lp-mock.play .lp-scanline { animation: lpScan 1.3s ease .35s both; }
    .lp-mock.play .lp-selo:nth-child(1) { animation: lpPop .4s cubic-bezier(.2,1.4,.4,1) 1.5s both; }
    .lp-mock.play .lp-selo:nth-child(2) { animation: lpPop .4s cubic-bezier(.2,1.4,.4,1) 2.1s both; }
    .lp-mock.play .lp-lei { animation: lpFadeup .55s ease 2.6s both; }
    .lp-mock.play .lp-dot { animation: lpPulse 1s ease infinite; }
    .lp-mock.play.done .lp-dot { animation: none; background: #16a34a; }
  }
  @media (prefers-reduced-motion: reduce) {
    .lp-selo, .lp-lei { opacity: 1; transform: none; }
  }
  @keyframes lpScan { 0% { left: -50%; opacity: 0; } 12% { opacity: 1; } 88% { opacity: 1; } 100% { left: 105%; opacity: 0; } }
  @keyframes lpPop { from { opacity: 0; transform: scale(.72); } to { opacity: 1; transform: scale(1); } }
  @keyframes lpFadeup { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  @keyframes lpPulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
  .lp-mock-legenda { font-size: 11.5px; color: #7c86a0; margin: 14px 6px 0; max-width: 460px; margin-left: auto; }

  /* ── Faixa das leis ─────────────────────────────────────────────────── */
  .lp-marquee { background: var(--deep); border-top: 1px solid var(--deep-line); padding: 15px 0; overflow: hidden; position: relative; }
  .lp-marquee::before, .lp-marquee::after {
    content: ""; position: absolute; top: 0; bottom: 0; width: 90px; z-index: 2; pointer-events: none;
  }
  .lp-marquee::before { left: 0; background: linear-gradient(90deg, var(--deep), transparent); }
  .lp-marquee::after { right: 0; background: linear-gradient(-90deg, var(--deep), transparent); }
  .lp-faixa { display: flex; gap: 38px; width: max-content; }
  .lp-faixa span { font-family: var(--mono); font-size: 11px; color: #66718c; white-space: nowrap; letter-spacing: .02em; }
  .lp-faixa b { color: #9aa5c0; font-weight: 600; }
  @media (prefers-reduced-motion: no-preference) {
    .lp-faixa { animation: lpRolar 42s linear infinite; }
    .lp-marquee:hover .lp-faixa { animation-play-state: paused; }
  }
  @keyframes lpRolar { to { transform: translateX(-50%); } }

  /* ── Comparação ─────────────────────────────────────────────────────── */
  .lp-seg { display: inline-flex; background: var(--mist); border: 1px solid var(--line); border-radius: 12px; padding: 4px; gap: 4px; margin-bottom: 22px; }
  .lp-seg button {
    padding: 9px 18px; border-radius: 9px; border: none; cursor: pointer;
    font-size: 13px; font-weight: 700; color: var(--slate); background: transparent;
    transition: background .2s, color .2s, box-shadow .2s;
  }
  .lp-seg button.on { background: white; color: var(--ink); box-shadow: 0 2px 10px rgba(11,18,32,.08); }
  .lp-painel { display: none; border-radius: 16px; padding: 24px 26px; }
  .lp-painel.on { display: block; animation: lpFadeup .35s ease both; }
  .lp-painel-generica { background: var(--mist); border: 1px solid var(--line); }
  .lp-painel-comp { background: white; border: 1px solid #c9d1fb; box-shadow: 0 10px 36px rgba(99,102,241,.1); position: relative; overflow: hidden; }
  .lp-painel-comp::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--grad); }
  .lp-quote { font-size: 14.5px; color: #66718c; font-style: italic; margin: 0 0 18px; max-width: 560px; }
  .lp-lacuna, .lp-ganho { display: flex; gap: 11px; align-items: flex-start; padding: 7px 0; max-width: 620px; }
  .lp-lacuna .lp-tick { width: 6px; height: 2px; background: #c3cad9; margin-top: 10px; flex-shrink: 0; border-radius: 1px; }
  .lp-lacuna span { font-size: 13.5px; color: #66718c; }
  .lp-ganho b { font-size: 13.5px; font-weight: 700; display: block; line-height: 1.4; }
  .lp-ganho small { font-size: 12.5px; color: #66718c; display: block; margin-top: 2px; line-height: 1.55; }

  /* ── Passos ─────────────────────────────────────────────────────────── */
  .lp-passos { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-top: 34px; counter-reset: lpPasso; }
  .lp-passo { background: white; border: 1px solid var(--line); border-radius: 14px; padding: 20px 20px 22px; position: relative; overflow: hidden; transition: transform .2s, box-shadow .2s, border-color .2s; }
  .lp-passo:hover { transform: translateY(-3px); border-color: #c9d1fb; box-shadow: 0 12px 32px rgba(99,102,241,.1); }
  .lp-passo::before { counter-increment: lpPasso; content: counter(lpPasso, decimal-leading-zero); font-family: var(--mono); font-size: 12px; font-weight: 700; color: var(--indigo); display: block; margin-bottom: 12px; }
  .lp-passo b { font-size: 14.5px; font-weight: 700; display: block; margin-bottom: 6px; line-height: 1.3; }
  .lp-passo p { font-size: 13px; color: #66718c; margin: 0; }

  /* ── Áreas ──────────────────────────────────────────────────────────── */
  .lp-areas { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 26px; }
  .lp-area { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: #33405c; border: 1px solid var(--line); border-radius: 10px; padding: 8px 14px; background: white; font-weight: 500; transition: border-color .15s, background .15s; }
  .lp-area:hover { border-color: #c9d1fb; background: #fafbff; }
  .lp-area b { font-size: 12px; font-weight: 800; color: var(--indigo); }
  .lp-callout { display: flex; gap: 12px; align-items: flex-start; margin-top: 26px; padding: 18px 20px; background: #eef2ff; border-radius: 14px; border: 1px solid #e0e7ff; font-size: 14px; color: #3730a3; max-width: 760px; }

  /* ── Governança ─────────────────────────────────────────────────────── */
  .lp-gov { background: var(--deep); color: white; position: relative; overflow: hidden; }
  .lp-gov::before { content: ""; position: absolute; inset: 0; pointer-events: none; background: radial-gradient(640px 360px at 88% 0%, rgba(139,92,246,.14), transparent 65%); }
  .lp-gov .lp-wrap { position: relative; }
  .lp-gov .lp-lede { color: #aab3c8; }
  .lp-bento { display: grid; grid-template-columns: 1.25fr 1fr 1fr; gap: 16px; margin-top: 34px; }
  .lp-cel { background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.09); border-radius: 16px; padding: 22px; backdrop-filter: blur(6px); position: relative; overflow: hidden; }
  .lp-spot::after {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    opacity: 0; transition: opacity .3s;
    background: radial-gradient(320px circle at var(--mx, 50%) var(--my, 50%), rgba(99,102,241,.16), transparent 65%);
  }
  .lp-spot:hover::after { opacity: 1; }
  .lp-cel b { font-size: 15px; font-weight: 700; display: block; margin: 12px 0 7px; }
  .lp-cel p { font-size: 13px; color: #9aa5c0; line-height: 1.65; margin: 0; }
  .lp-cel-icone { width: 38px; height: 38px; border-radius: 11px; background: rgba(99,102,241,.16); border: 1px solid rgba(99,102,241,.3); display: grid; place-items: center; }
  .lp-minilog { margin-top: 14px; border-top: 1px solid rgba(255,255,255,.08); padding-top: 12px; font-family: var(--mono); font-size: 10.5px; }
  .lp-minilog div { display: flex; gap: 10px; padding: 4px 0; color: #7c86a0; }
  .lp-minilog b { display: inline; margin: 0; font-size: 10.5px; font-weight: 600; color: #b6bfd6; }

  /* ── Honestidade ────────────────────────────────────────────────────── */
  .lp-limites { display: grid; grid-template-columns: 1fr 1fr; gap: 18px 30px; margin-top: 30px; }
  .lp-limite { display: flex; gap: 12px; align-items: flex-start; }
  .lp-limite b { font-size: 14.5px; font-weight: 700; display: block; margin-bottom: 4px; }
  .lp-limite p { font-size: 13.5px; color: #66718c; margin: 0; }

  /* ── Fecho e rodapé ─────────────────────────────────────────────────── */
  .lp-fecho { background: var(--deep); color: white; position: relative; overflow: hidden; }
  .lp-fecho::before { content: ""; position: absolute; inset: 0; pointer-events: none; background: radial-gradient(700px 380px at 18% 0%, rgba(99,102,241,.18), transparent 65%); }
  .lp-fecho .lp-wrap { position: relative; }
  .lp-fecho .lp-lede { color: #aab3c8; margin-bottom: 34px; }
  .lp-foot { background: var(--deep); border-top: 1px solid var(--deep-line); padding: 24px 0 32px; }
  .lp-foot-in { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-size: 12.5px; color: #66718c; }

  @media (max-width: 960px) {
    .lp-hero .lp-wrap { grid-template-columns: 1fr; }
    .lp-halo { margin-left: 0; }
    .lp-passos { grid-template-columns: 1fr 1fr; }
    .lp-bento { grid-template-columns: 1fr; }
    .lp-limites { grid-template-columns: 1fr; }
  }
  @media (max-width: 560px) {
    .lp-passos { grid-template-columns: 1fr; }
    .lp-cta-linha > button { width: 100%; justify-content: center; }
  }
`;

// ─── Ícones (SVG inline, sem dependências) ───────────────────────────────────

const svgProps = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };

const IcoEscudo = ({ size = 15 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...svgProps} stroke="white" strokeWidth={2.2}>
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
  </svg>
);

const IcoCheck = ({ size = 11, cor = "currentColor", peso = 2.6, style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...svgProps} stroke={cor} strokeWidth={peso} style={style}>
    <path d="M21.8 10A10 10 0 1 1 17 3.34" /><path d="m9 11 3 3L22 4" />
  </svg>
);

const IcoSeta = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...svgProps} strokeWidth={2.4}>
    <path d="M5 12h14" /><path d="m12 5 7 7-7 7" />
  </svg>
);

const IcoBalanca = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" {...svgProps} stroke="#a5b4fc">
    <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
    <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
    <path d="M7 21h10" /><path d="M12 3v18" />
    <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
  </svg>
);

const IcoArquivo = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" {...svgProps} stroke="#6366f1">
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
  </svg>
);

const IcoBusca = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...svgProps} stroke="#6366f1" style={{ flexShrink: 0, marginTop: 2 }}>
    <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
  </svg>
);

const IcoRelogio = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" {...svgProps} stroke="#a5b4fc">
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" /><path d="M12 7v5l4 2" />
  </svg>
);

const IcoCadeado = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" {...svgProps} stroke="#a5b4fc">
    <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

const IcoArquiva = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" {...svgProps} stroke="#a5b4fc">
    <rect width="20" height="5" x="2" y="3" rx="1" />
    <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" />
  </svg>
);

const IcoAviso = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" {...svgProps} stroke="#8a93a8" style={{ flexShrink: 0, marginTop: 3 }}>
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
    <path d="M12 9v4" /><path d="M12 17h.01" />
  </svg>
);

// ─── Página ──────────────────────────────────────────────────────────────────

export default function LandingPage({ onEntrar, onCriarConta }) {
  const raizRef = useRef(null);
  const mockRef = useRef(null);
  const statusRef = useRef(null);
  const timerMockRef = useRef(null);
  const [painel, setPainel] = useState("generica");

  const reduzMotion = () =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // A sequência do cartão: varredura, selos, texto da lei, status.
  const verificar = useCallback(() => {
    const mock = mockRef.current;
    const status = statusRef.current;
    if (!mock || !status) return;
    clearTimeout(timerMockRef.current);
    mock.classList.remove("play", "done");
    status.textContent = "verificando…";
    if (reduzMotion()) {
      status.textContent = "2 verificações concluídas";
      mock.classList.add("done");
      return;
    }
    void mock.offsetWidth; // reflow reinicia as animações CSS
    mock.classList.add("play");
    timerMockRef.current = setTimeout(() => {
      status.textContent = "2 verificações concluídas";
      mock.classList.add("done");
    }, 3200);
  }, []);

  useEffect(() => {
    const raiz = raizRef.current;
    if (!raiz) return;
    const observers = [];
    const timers = [];

    // Revelação ao rolar.
    const ioReveal = new IntersectionObserver((es) => {
      for (const e of es) {
        if (e.isIntersecting) { e.target.classList.add("on"); ioReveal.unobserve(e.target); }
      }
    }, { threshold: 0.12 });
    raiz.querySelectorAll(".reveal").forEach((el) => ioReveal.observe(el));
    observers.push(ioReveal);

    // Contagem dos números do herói.
    const fmtPt = new Intl.NumberFormat("pt-BR");
    const contar = (el) => {
      const alvo = parseInt(el.dataset.n, 10);
      const pt = el.dataset.fmt === "pt";
      if (reduzMotion()) { el.textContent = pt ? fmtPt.format(alvo) : String(alvo); return; }
      const t0 = performance.now();
      const dur = 1100;
      const passo = (t) => {
        const p = Math.min((t - t0) / dur, 1);
        const suave = 1 - Math.pow(1 - p, 3);
        const v = Math.round(alvo * suave);
        el.textContent = pt ? fmtPt.format(v) : String(v);
        if (p < 1) requestAnimationFrame(passo);
      };
      requestAnimationFrame(passo);
    };
    const ioNum = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) { contar(e.target); ioNum.unobserve(e.target); }
    }, { threshold: 0.6 });
    raiz.querySelectorAll(".lp-num-v").forEach((el) => ioNum.observe(el));
    observers.push(ioNum);

    // O cartão dispara quando entra na tela.
    const ioMock = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) { verificar(); ioMock.unobserve(e.target); }
    }, { threshold: 0.4 });
    if (mockRef.current) ioMock.observe(mockRef.current);
    observers.push(ioMock);

    // A comparação demonstra a alternância uma vez: abre na genérica e vira
    // para o ComplianceAI, que é a revelação do argumento.
    const dif = raiz.querySelector("#diferencial");
    if (dif) {
      const ioSeg = new IntersectionObserver((es) => {
        for (const e of es) {
          if (e.isIntersecting) {
            if (reduzMotion()) setPainel("comp");
            else timers.push(setTimeout(() => setPainel("comp"), 1900));
            ioSeg.unobserve(e.target);
          }
        }
      }, { threshold: 0.5 });
      ioSeg.observe(dif);
      observers.push(ioSeg);
    }

    // Spotlight: o brilho segue o cursor dentro do cartão.
    const aoMover = (ev) => {
      const el = ev.currentTarget;
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${ev.clientX - r.left}px`);
      el.style.setProperty("--my", `${ev.clientY - r.top}px`);
    };
    const spots = [...raiz.querySelectorAll(".lp-spot")];
    spots.forEach((el) => el.addEventListener("pointermove", aoMover));

    return () => {
      observers.forEach((o) => o.disconnect());
      timers.forEach(clearTimeout);
      clearTimeout(timerMockRef.current);
      spots.forEach((el) => el.removeEventListener("pointermove", aoMover));
    };
  }, [verificar]);

  const rolarAoTopo = () => window.scrollTo({ top: 0, behavior: "smooth" });

  return (
    <div className="lp-root" ref={raizRef}>
      <style>{CSS}</style>

      {/* ── Navegação em pílula ─────────────────────────────────────────── */}
      <nav className="lp-nav">
        <div className="lp-nav-in">
          <button className="lp-logo" onClick={rolarAoTopo} aria-label="Voltar ao topo">
            <span className="lp-logo-badge"><IcoEscudo /></span>
            <b>ComplianceAI</b>
          </button>
          <div className="lp-nav-links" aria-label="Seções">
            <a href="#diferencial">Diferencial</a>
            <a href="#como-funciona">Como funciona</a>
            <a href="#escritorios">Para escritórios</a>
          </div>
          <div className="lp-nav-acoes">
            <button className="lp-nav-entrar" onClick={onEntrar}>Entrar</button>
            <button className="lp-nav-cta" onClick={onCriarConta}>Criar conta</button>
          </div>
        </div>
      </nav>

      {/* ── Herói ───────────────────────────────────────────────────────── */}
      <header className="lp-hero" id="topo">
        <div className="lp-aurora lp-aurora-a" />
        <div className="lp-aurora lp-aurora-b" />
        <div className="lp-wrap">
          <div>
            <div className="lp-hero-badge reveal">
              <IcoBalanca /> Conformidade contratual sob a legislação brasileira
            </div>
            <h1 className="reveal d1">
              Revisão de contrato com IA que mostra{" "}
              <span className="lp-grad-text">onde conferir</span>.
            </h1>
            <p className="lp-lede reveal d2">
              Envie o contrato e receba, em minutos, as cláusulas problemáticas:
              cada alerta aponta o trecho exato, a página em que ele está e o
              artigo de lei que o sustenta. O sistema confere tudo isso sozinho
              antes de mostrar.
            </p>
            <div className="lp-cta-linha reveal d3">
              <button className="lp-cta" onClick={onCriarConta}>
                Analisar um contrato <IcoSeta />
              </button>
              <button className="lp-ghost escuro" onClick={onEntrar}>Já tenho conta</button>
            </div>
            <div className="lp-nums reveal d4">
              <div>
                <div className="lp-num-v" data-n="3927" data-fmt="pt">0</div>
                <div className="lp-num-l">artigos de lei indexados</div>
              </div>
              <div>
                <div className="lp-num-v" data-n="10">0</div>
                <div className="lp-num-l">leis brasileiras na íntegra</div>
              </div>
              <div>
                <div className="lp-num-v" data-n="29">0</div>
                <div className="lp-num-l">verificações configuráveis</div>
              </div>
            </div>
          </div>

          <div className="reveal d3">
            <div className="lp-halo">
              <div className="lp-mock" ref={mockRef}>
                <div className="lp-mock-top">
                  <div className="lp-mock-file">
                    <IcoArquivo /><span>contrato-locacao-comercial.pdf</span>
                  </div>
                  <span className="lp-pill lp-pill-risco">Risco 78</span>
                </div>
                <div className="lp-mock-body">
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    <span className="lp-pill lp-pill-sev">Severidade alta</span>
                    <span className="lp-pill lp-pill-area">Locação</span>
                  </div>
                  <div className="lp-mock-alert-t">Renúncia à ação renovatória</div>
                  <div className="lp-excerpt">
                    "A LOCATÁRIA declara, desde já, renunciar expressa e
                    irrevogavelmente ao direito de renovação compulsória da locação"
                    <span className="lp-scanline" />
                  </div>
                  <div className="lp-selos">
                    <span className="lp-selo"><IcoCheck /> Trecho conferido, pág. 1</span>
                    <span className="lp-selo"><IcoCheck /> Artigo conferido na base</span>
                  </div>
                  <div className="lp-lei">
                    <b>Art. 51, Lei 8.245/1991</b>
                    <p>
                      Nas locações de imóveis destinados ao comércio, o locatário
                      terá direito a renovação do contrato, por igual prazo, desde
                      que preenchidos os requisitos legais.
                    </p>
                  </div>
                </div>
                <div className="lp-mock-foot">
                  <span className="lp-status">
                    <span className="lp-dot" /><span ref={statusRef}>verificando…</span>
                  </span>
                  <button className="lp-replay" type="button" onClick={verificar}>ver de novo</button>
                </div>
              </div>
            </div>
            <p className="lp-mock-legenda">
              Alerta real de uma análise. Os selos verdes são o sistema
              conferindo, em código, o que a IA afirmou.
            </p>
          </div>
        </div>
      </header>

      {/* ── Faixa das dez leis ──────────────────────────────────────────── */}
      <div className="lp-marquee" aria-hidden="true">
        <div className="lp-faixa">
          {[...LEIS, ...LEIS].map(([sigla, numero], i) => (
            <span key={i}><b>{sigla}</b> · {numero}</span>
          ))}
        </div>
      </div>

      {/* ── O problema ──────────────────────────────────────────────────── */}
      <section className="lp-sec" style={{ background: "#f6f7fb" }}>
        <div className="lp-wrap">
          <div className="lp-eyebrow reveal">O problema</div>
          <h2 className="reveal">A parte cara da revisão não é ler. É não deixar passar.</h2>
          <p className="lp-lede reveal">
            Um contrato de vinte páginas tem uma dúzia de armadilhas conhecidas:
            foro eleito em comarca distante, multa sem proporcionalidade, renúncia
            a direito que não se renuncia, dados pessoais sem finalidade definida,
            garantia cumulada onde a lei permite uma só.
          </p>
          <p className="lp-lede reveal" style={{ marginTop: 14 }}>
            São sempre as mesmas, e é justamente por isso que escapam. Depois do
            quinto contrato da semana a leitura vira varredura, e o custo de cada
            erro não é seu. É do cliente.
          </p>
        </div>
      </section>

      {/* ── O diferencial ───────────────────────────────────────────────── */}
      <section className="lp-sec" id="diferencial">
        <div className="lp-wrap">
          <div className="lp-eyebrow reveal">O diferencial</div>
          <h2 className="reveal">Por que não jogar o contrato no ChatGPT?</h2>
          <p className="lp-lede reveal" style={{ marginBottom: 26 }}>
            Porque uma IA de uso geral responde com a mesma confiança quando
            acerta e quando inventa. Compare o mesmo alerta nas duas:
          </p>

          <div className="reveal">
            <div className="lp-seg" role="tablist">
              <button
                type="button"
                role="tab"
                className={painel === "generica" ? "on" : ""}
                onClick={() => setPainel("generica")}
              >
                IA de uso geral
              </button>
              <button
                type="button"
                role="tab"
                className={painel === "comp" ? "on" : ""}
                onClick={() => setPainel("comp")}
              >
                ComplianceAI
              </button>
            </div>

            <div className={`lp-painel lp-painel-generica ${painel === "generica" ? "on" : ""}`}>
              <p className="lp-quote">
                "A cláusula sexta pode violar a legislação de locações.
                Recomenda-se a adequação dos termos contratuais conforme a Lei nº
                8.245/1991."
              </p>
              {LACUNAS.map((t) => (
                <div className="lp-lacuna" key={t}>
                  <span className="lp-tick" /><span>{t}</span>
                </div>
              ))}
            </div>

            <div className={`lp-painel lp-painel-comp ${painel === "comp" ? "on" : ""}`}>
              {GANHOS.map(([t, d]) => (
                <div className="lp-ganho" key={t}>
                  <IcoCheck size={15} cor="#15803d" peso={2.4} style={{ flexShrink: 0, marginTop: 2.5 }} />
                  <span><b>{t}</b><small>{d}</small></span>
                </div>
              ))}
            </div>
          </div>

          <p className="lp-lede reveal" style={{ marginTop: 24, fontSize: 14 }}>
            A diferença não está no texto do alerta. Está em ele se deixar
            conferir: quando o sistema não localiza o que a IA afirmou, ele diz
            isso na tela, em vez de deixar você descobrir na frente do cliente.
          </p>
        </div>
      </section>

      {/* ── Como funciona ───────────────────────────────────────────────── */}
      <section className="lp-sec" id="como-funciona" style={{ background: "#f6f7fb" }}>
        <div className="lp-wrap">
          <div className="lp-eyebrow reveal">Como funciona</div>
          <h2 className="reveal">Do upload ao relatório, em quatro passos.</h2>
          <div className="lp-passos reveal">
            {PASSOS.map(([t, d]) => (
              <div className="lp-passo lp-spot" key={t}><b>{t}</b><p>{d}</p></div>
            ))}
          </div>
          <p className="lp-lede reveal" style={{ marginTop: 26, fontSize: 14 }}>
            O resultado sai na tela e em PDF, com os mesmos selos de verificação.
            Cada revisor marca os alertas como a corrigir, não se aplica ou
            resolvido, e o relatório sai com a marcação de quem o exporta.
          </p>
        </div>
      </section>

      {/* ── O que ele verifica ──────────────────────────────────────────── */}
      <section className="lp-sec">
        <div className="lp-wrap">
          <div className="lp-eyebrow reveal">O que ele verifica</div>
          <h2 className="reveal">Vinte e nove verificações, organizadas por área do direito.</h2>
          <p className="lp-lede reveal">
            As que valem para qualquer contrato vêm ligadas. As de área específica
            ficam desligadas até você precisar, porque regra de locação em
            contrato de tecnologia só produz alarme falso. Uma área inteira liga
            em um clique.
          </p>
          <div className="lp-areas reveal">
            {AREAS.map(([n, nome]) => (
              <span className="lp-area" key={nome}><b>{n}</b> {nome}</span>
            ))}
          </div>
          <div className="lp-callout reveal">
            <IcoBusca />
            <span>
              E as regras do seu escritório entram no jogo: prazo máximo de
              pagamento, foro obrigatório, teto de multa. Vira uma regra uma vez e
              passa a ser verificado em todo contrato, sem ninguém precisar
              lembrar.
            </span>
          </div>
        </div>
      </section>

      {/* ── Governança ──────────────────────────────────────────────────── */}
      <section className="lp-sec lp-gov" id="escritorios">
        <div className="lp-wrap">
          <div className="lp-eyebrow claro reveal">Feito para escritórios</div>
          <h2 className="reveal">O contrato do seu cliente não circula pelo escritório inteiro.</h2>
          <p className="lp-lede reveal">
            O texto é processado por um modelo de IA operado por terceiro, aqui e
            em qualquer ferramenta do gênero. A diferença está no que existe em
            volta: quem pode abrir, o que fica registrado e por quanto tempo se
            guarda.
          </p>
          <div className="lp-bento reveal">
            <div className="lp-cel lp-spot">
              <div className="lp-cel-icone"><IcoRelogio /></div>
              <b>Registro de acesso</b>
              <p>
                Quem leu, baixou ou exportou, e quando. O registro permanece mesmo
                depois que o documento é apagado, que é quando a auditoria mais
                precisa dele.
              </p>
              <div className="lp-minilog">
                <div><b>14:02</b> Ana leu o relatório</div>
                <div><b>14:07</b> Bruno baixou o original</div>
                <div><b>14:31</b> Ana exportou o PDF</div>
              </div>
            </div>
            <div className="lp-cel lp-spot">
              <div className="lp-cel-icone"><IcoCadeado /></div>
              <b>Sigilo por cliente</b>
              <p>
                Cada contrato pertence a um cliente, e só o abre quem foi
                designado a ele. Quem não foi nem descobre que o cliente existe.
              </p>
            </div>
            <div className="lp-cel lp-spot">
              <div className="lp-cel-icone"><IcoArquiva /></div>
              <b>Prazo de guarda</b>
              <p>
                Definido por cliente. Vencido o prazo, o documento entra numa fila
                de revisão. Nada é apagado sem alguém confirmar.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Honestidade ─────────────────────────────────────────────────── */}
      <section className="lp-sec">
        <div className="lp-wrap">
          <div className="lp-eyebrow reveal">Para ser justo</div>
          <h2 className="reveal">O que ele não faz.</h2>
          <p className="lp-lede reveal">
            Dizemos antes porque ferramenta que promete demais é desmascarada no
            primeiro contrato difícil, e a confiança que sustenta os selos verdes
            é a mesma que se perderia ali.
          </p>
          <div className="lp-limites reveal">
            {LIMITES.map(([t, d]) => (
              <div className="lp-limite" key={t}>
                <IcoAviso />
                <span><b>{t}</b><p>{d}</p></span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Fecho ───────────────────────────────────────────────────────── */}
      <section className="lp-sec lp-fecho">
        <div className="lp-wrap">
          <div className="lp-eyebrow claro reveal">Comece agora</div>
          <h2 className="reveal" style={{ maxWidth: 560 }}>
            Teste com um contrato que você já revisou.
          </h2>
          <p className="lp-lede reveal" style={{ maxWidth: 600 }}>
            É a forma mais rápida de julgar a ferramenta: passe por ela um
            contrato cujo resultado você conhece e compare com o que tinha
            anotado. O que ela pegou, o que deixou passar e o que apontou a mais.
          </p>
          <div className="lp-cta-linha reveal" style={{ marginBottom: 0 }}>
            <button className="lp-cta" onClick={onCriarConta}>
              Criar conta e analisar <IcoSeta />
            </button>
            <button className="lp-ghost escuro" onClick={onEntrar}>Entrar</button>
          </div>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-wrap lp-foot-in">
          <span>ComplianceAI · Recife, PE</span>
          <span>Análise de conformidade contratual com IA</span>
        </div>
      </footer>
    </div>
  );
}
