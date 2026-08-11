"""
Consolidated legal database seed — creates one legal_document per law
and inserts legal_chunk rows for each article.

Architecture:
  legal_documents: 1 row per law (LGPD, CDC, CLT, etc.)
  legal_chunks:    1 row per article, linked to parent document

Idempotent: skips laws that already have chunks.
Embeddings are NOT generated here (requires OpenAI API).
"""

import sys, os, uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from app.core.config import Settings

settings = Settings()


def get_sync_engine():
    db_url = str(settings.DATABASE_URL)
    if db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    return create_engine(db_url, echo=False)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA — Each law is { title, source, category, articles: [{ ref, title, content }] }
# ═══════════════════════════════════════════════════════════════════════════════

LAWS = [
    {
        "title": "LGPD - Lei Geral de Proteção de Dados",
        "source": "Lei 13.709/2018",
        "category": "proteção_de_dados",
        "articles": [
            {"ref": "Art. 1º", "title": "Objeto da Lei", "content": "Art. 1º Esta Lei dispõe sobre o tratamento de dados pessoais, inclusive nos meios digitais, por pessoa natural ou por pessoa jurídica de direito público ou privado, com o objetivo de proteger os direitos fundamentais de liberdade e de privacidade e o livre desenvolvimento da personalidade da pessoa natural.\n\nParágrafo único. As normas gerais contidas nesta Lei são de interesse nacional e devem ser observadas pela União, Estados, Distrito Federal e Municípios."},
            {"ref": "Art. 2º", "title": "Fundamentos", "content": "Art. 2º A disciplina da proteção de dados pessoais tem como fundamentos:\nI - o respeito à privacidade;\nII - a autodeterminação informativa;\nIII - a liberdade de expressão, de informação, de comunicação e de opinião;\nIV - a inviolabilidade da intimidade, da honra e da imagem;\nV - o desenvolvimento econômico e tecnológico e a inovação;\nVI - a livre iniciativa, a livre concorrência e a defesa do consumidor;\nVII - os direitos humanos, o livre desenvolvimento da personalidade, a dignidade e o exercício da cidadania pelas pessoas naturais."},
            {"ref": "Art. 5º", "title": "Definições", "content": "Art. 5º Para os fins desta Lei, considera-se:\nI - dado pessoal: informação relacionada a pessoa natural identificada ou identificável;\nII - dado pessoal sensível: dado pessoal sobre origem racial ou étnica, convicção religiosa, opinião política, filiação a sindicato ou a organização de caráter religioso, filosófico ou político, dado referente à saúde ou à vida sexual, dado genético ou biométrico;\nIII - dado anonimizado: dado relativo a titular que não possa ser identificado;\nIV - banco de dados: conjunto estruturado de dados pessoais;\nV - titular: pessoa natural a quem se referem os dados pessoais;\nVI - controlador: pessoa a quem competem as decisões referentes ao tratamento;\nVII - operador: pessoa que realiza o tratamento em nome do controlador;\nVIII - encarregado: pessoa indicada como canal de comunicação entre controlador, titulares e ANPD;\nIX - agentes de tratamento: o controlador e o operador;\nX - tratamento: toda operação realizada com dados pessoais;\nXI - anonimização: utilização de meios técnicos para perda de associação a indivíduo;\nXII - consentimento: manifestação livre, informada e inequívoca do titular."},
            {"ref": "Art. 7º", "title": "Bases Legais para Tratamento", "content": "Art. 7º O tratamento de dados pessoais somente poderá ser realizado nas seguintes hipóteses:\nI - mediante o fornecimento de consentimento pelo titular;\nII - para o cumprimento de obrigação legal ou regulatória pelo controlador;\nIII - pela administração pública, para execução de políticas públicas;\nIV - para a realização de estudos por órgão de pesquisa;\nV - para a execução de contrato do qual seja parte o titular;\nVI - para o exercício regular de direitos em processo judicial, administrativo ou arbitral;\nVII - para a proteção da vida ou da incolumidade física;\nVIII - para a tutela da saúde;\nIX - para atender aos interesses legítimos do controlador ou de terceiro;\nX - para a proteção do crédito."},
            {"ref": "Art. 11", "title": "Tratamento de Dados Sensíveis", "content": "Art. 11. O tratamento de dados pessoais sensíveis somente poderá ocorrer nas seguintes hipóteses:\nI - quando o titular ou seu responsável legal consentir de forma específica e destacada, para finalidades específicas;\nII - sem fornecimento de consentimento do titular, nas hipóteses em que for indispensável para:\na) cumprimento de obrigação legal ou regulatória pelo controlador;\nb) tratamento compartilhado de dados necessários à execução de políticas públicas;\nc) realização de estudos por órgão de pesquisa;\nd) exercício regular de direitos;\ne) proteção da vida ou da incolumidade física;\nf) tutela da saúde;\ng) garantia da prevenção à fraude e à segurança do titular."},
            {"ref": "Art. 18", "title": "Direitos do Titular", "content": "Art. 18. O titular dos dados pessoais tem direito a obter do controlador, a qualquer momento e mediante requisição:\nI - confirmação da existência de tratamento;\nII - acesso aos dados;\nIII - correção de dados incompletos, inexatos ou desatualizados;\nIV - anonimização, bloqueio ou eliminação de dados desnecessários ou excessivos;\nV - portabilidade dos dados a outro fornecedor de serviço ou produto;\nVI - eliminação dos dados pessoais tratados com o consentimento do titular;\nVII - informação das entidades com as quais o controlador realizou uso compartilhado;\nVIII - informação sobre a possibilidade de não fornecer consentimento e as consequências;\nIX - revogação do consentimento."},
            {"ref": "Art. 46", "title": "Segurança e Sigilo dos Dados", "content": "Art. 46. Os agentes de tratamento devem adotar medidas de segurança, técnicas e administrativas aptas a proteger os dados pessoais de acessos não autorizados e de situações acidentais ou ilícitas de destruição, perda, alteração, comunicação ou qualquer forma de tratamento inadequado ou ilícito.\n\n§ 1º A autoridade nacional poderá dispor sobre padrões técnicos mínimos.\n§ 2º As medidas deverão ser observadas desde a fase de concepção do produto ou do serviço até a sua execução."},
            {"ref": "Art. 48", "title": "Comunicação de Incidentes", "content": "Art. 48. O controlador deverá comunicar à autoridade nacional e ao titular a ocorrência de incidente de segurança que possa acarretar risco ou dano relevante aos titulares.\n\n§ 1º A comunicação deverá mencionar:\nI - a descrição da natureza dos dados pessoais afetados;\nII - as informações sobre os titulares envolvidos;\nIII - as medidas técnicas e de segurança utilizadas;\nIV - os riscos relacionados ao incidente;\nV - os motivos da demora, se houver;\nVI - as medidas adotadas para reverter ou mitigar os efeitos do prejuízo."},
            {"ref": "Art. 52", "title": "Sanções Administrativas", "content": "Art. 52. Os agentes de tratamento ficam sujeitos às seguintes sanções administrativas:\nI - advertência, com prazo para medidas corretivas;\nII - multa simples de até 2% do faturamento, limitada a R$ 50.000.000,00 por infração;\nIII - multa diária;\nIV - publicização da infração;\nV - bloqueio dos dados pessoais;\nVI - eliminação dos dados pessoais;\nX - suspensão parcial do banco de dados por até 6 meses;\nXI - suspensão do exercício da atividade de tratamento;\nXII - proibição parcial ou total do exercício de atividades relacionadas a tratamento de dados."},
        ],
    },
    {
        "title": "Código de Defesa do Consumidor",
        "source": "Lei 8.078/1990 (CDC)",
        "category": "consumidor",
        "articles": [
            {"ref": "Art. 6º", "title": "Direitos Básicos do Consumidor", "content": "Art. 6º São direitos básicos do consumidor:\nI - a proteção da vida, saúde e segurança;\nII - a educação e divulgação sobre o consumo adequado dos produtos e serviços;\nIII - a informação adequada e clara sobre os diferentes produtos e serviços;\nIV - a proteção contra a publicidade enganosa e abusiva;\nV - a modificação das cláusulas contratuais que estabeleçam prestações desproporcionais;\nVI - a efetiva prevenção e reparação de danos patrimoniais e morais;\nVII - o acesso aos órgãos judiciários e administrativos;\nVIII - a facilitação da defesa de seus direitos;\nIX - a adequada e eficaz prestação dos serviços públicos em geral;\nX - a garantia de práticas de crédito responsável."},
            {"ref": "Art. 14", "title": "Responsabilidade por Defeito na Prestação do Serviço", "content": "Art. 14. O fornecedor de serviços responde, independentemente da existência de culpa, pela reparação dos danos causados aos consumidores por defeitos relativos à prestação dos serviços, bem como por informações insuficientes ou inadequadas sobre sua fruição e riscos.\n\n§ 1º O serviço é defeituoso quando não fornece a segurança que o consumidor dele pode esperar.\n§ 2º O serviço não é considerado defeituoso pela adoção de novas técnicas.\n§ 3º O fornecedor de serviços só não será responsabilizado quando provar que não existe o defeito ou a culpa exclusiva do consumidor ou de terceiro.\n§ 4º A responsabilidade pessoal dos profissionais liberais será apurada mediante a verificação de culpa."},
            {"ref": "Art. 18", "title": "Responsabilidade por Vício do Produto", "content": "Art. 18. Os fornecedores de produtos de consumo duráveis ou não duráveis respondem solidariamente pelos vícios de qualidade ou quantidade que os tornem impróprios ou inadequados ao consumo a que se destinam ou lhes diminuam o valor.\n\n§ 1º Não sendo o vício sanado no prazo máximo de trinta dias, pode o consumidor exigir, alternativamente:\nI - a substituição do produto por outro da mesma espécie;\nII - a restituição imediata da quantia paga, monetariamente atualizada;\nIII - o abatimento proporcional do preço."},
            {"ref": "Art. 30", "title": "Oferta Vinculante", "content": "Art. 30. Toda informação ou publicidade, suficientemente precisa, veiculada por qualquer forma ou meio de comunicação com relação a produtos e serviços oferecidos ou apresentados, obriga o fornecedor que a fizer veicular ou dela se utilizar e integra o contrato que vier a ser celebrado."},
            {"ref": "Art. 35", "title": "Descumprimento da Oferta", "content": "Art. 35. Se o fornecedor de produtos ou serviços recusar cumprimento à oferta, apresentação ou publicidade, o consumidor poderá, alternativamente e à sua livre escolha:\nI - exigir o cumprimento forçado da obrigação;\nII - aceitar outro produto ou prestação de serviço equivalente;\nIII - rescindir o contrato, com direito à restituição de quantia eventualmente antecipada, monetariamente atualizada, e a perdas e danos."},
            {"ref": "Art. 39", "title": "Práticas Abusivas", "content": "Art. 39. É vedado ao fornecedor de produtos ou serviços, dentre outras práticas abusivas:\nI - condicionar o fornecimento de produto ou serviço ao fornecimento de outro (venda casada);\nII - recusar atendimento às demandas dos consumidores;\nIII - enviar ou entregar ao consumidor produto ou serviço sem solicitação prévia;\nIV - prevalecer-se da fraqueza ou ignorância do consumidor;\nV - exigir do consumidor vantagem manifestamente excessiva;\nVI - executar serviços sem a prévia elaboração de orçamento;\nVII - repassar informação depreciativa referente a ato praticado pelo consumidor;\nVIII - colocar no mercado produto em desacordo com as normas;\nIX - recusar a venda de bens ou a prestação de serviços ao consumidor que se disponha a adquiri-los mediante pronto pagamento;\nX - elevar sem justa causa o preço de produtos ou serviços."},
            {"ref": "Art. 46", "title": "Proteção Contratual", "content": "Art. 46. Os contratos que regulam as relações de consumo não obrigarão os consumidores, se não lhes for dada a oportunidade de tomar conhecimento prévio de seu conteúdo, ou se os respectivos instrumentos forem redigidos de modo a dificultar a compreensão de seu sentido e alcance."},
            {"ref": "Art. 51", "title": "Cláusulas Abusivas", "content": "Art. 51. São nulas de pleno direito, entre outras, as cláusulas contratuais relativas ao fornecimento de produtos e serviços que:\nI - impossibilitem, exonerem ou atenuem a responsabilidade do fornecedor;\nII - subtraiam ao consumidor a opção de reembolso;\nIII - transfiram responsabilidades a terceiros;\nIV - estabeleçam obrigações iníquas ou abusivas que coloquem o consumidor em desvantagem exagerada;\nVI - estabeleçam inversão do ônus da prova em prejuízo do consumidor;\nVII - determinem a utilização compulsória de arbitragem;\nVIII - imponham representante para concluir ou realizar outro negócio jurídico pelo consumidor;\nXV - estejam em desacordo com o sistema de proteção ao consumidor."},
        ],
    },
    {
        "title": "Código Civil Brasileiro",
        "source": "Lei 10.406/2002",
        "category": "civil",
        "articles": [
            {"ref": "Art. 104", "title": "Requisitos do Negócio Jurídico", "content": "Art. 104. A validade do negócio jurídico requer:\nI - agente capaz;\nII - objeto lícito, possível, determinado ou determinável;\nIII - forma prescrita ou não defesa em lei."},
            {"ref": "Art. 186", "title": "Ato Ilícito", "content": "Art. 186. Aquele que, por ação ou omissão voluntária, negligência ou imprudência, violar direito e causar dano a outrem, ainda que exclusivamente moral, comete ato ilícito."},
            {"ref": "Art. 389", "title": "Inadimplemento das Obrigações", "content": "Art. 389. Não cumprida a obrigação, responde o devedor por perdas e danos, mais juros e atualização monetária segundo índices oficiais regularmente estabelecidos, e honorários de advogado."},
            {"ref": "Art. 421", "title": "Liberdade Contratual", "content": "Art. 421. A liberdade contratual será exercida nos limites da função social do contrato.\n\nParágrafo único. Nas relações contratuais privadas, prevalecerão o princípio da intervenção mínima e a excepcionalidade da revisão contratual."},
            {"ref": "Art. 422", "title": "Boa-fé Contratual", "content": "Art. 422. Os contratantes são obrigados a guardar, assim na conclusão do contrato, como em sua execução, os princípios de probidade e boa-fé."},
            {"ref": "Art. 423", "title": "Contrato de Adesão", "content": "Art. 423. Quando houver no contrato de adesão cláusulas ambíguas ou contraditórias, dever-se-á adotar a interpretação mais favorável ao aderente."},
            {"ref": "Art. 425", "title": "Contratos Atípicos", "content": "Art. 425. É lícito às partes estipular contratos atípicos, observadas as normas gerais fixadas neste Código."},
            {"ref": "Art. 427", "title": "Proposta de Contrato", "content": "Art. 427. A proposta de contrato obriga o proponente, se o contrário não resultar dos termos dela, da natureza do negócio, ou das circunstâncias do caso."},
            {"ref": "Art. 478", "title": "Resolução por Onerosidade Excessiva", "content": "Art. 478. Nos contratos de execução continuada ou diferida, se a prestação de uma das partes se tornar excessivamente onerosa, com extrema vantagem para a outra, em virtude de acontecimentos extraordinários e imprevisíveis, poderá o devedor pedir a resolução do contrato."},
            {"ref": "Art. 927", "title": "Responsabilidade Civil", "content": "Art. 927. Aquele que, por ato ilícito, causar dano a outrem, fica obrigado a repará-lo.\n\nParágrafo único. Haverá obrigação de reparar o dano, independentemente de culpa, nos casos especificados em lei, ou quando a atividade normalmente desenvolvida pelo autor do dano implicar, por sua natureza, risco para os direitos de outrem."},
        ],
    },
    {
        "title": "Consolidação das Leis do Trabalho",
        "source": "Decreto-Lei 5.452/1943 (CLT)",
        "category": "trabalhista",
        "articles": [
            {"ref": "Art. 2º", "title": "Definição de Empregador", "content": "Art. 2º Considera-se empregador a empresa, individual ou coletiva, que, assumindo os riscos da atividade econômica, admite, assalaria e dirige a prestação pessoal de serviço.\n\n§ 1º Equiparam-se ao empregador, para os efeitos exclusivos da relação de emprego, os profissionais liberais, as instituições de beneficência, as associações recreativas ou outras instituições sem fins lucrativos, que admitirem trabalhadores como empregados."},
            {"ref": "Art. 3º", "title": "Definição de Empregado", "content": "Art. 3º Considera-se empregado toda pessoa física que prestar serviços de natureza não eventual a empregador, sob a dependência deste e mediante salário.\n\nParágrafo único. Não haverá distinções relativas à espécie de emprego e à condição de trabalhador, nem entre o trabalho intelectual, técnico e manual."},
            {"ref": "Art. 58", "title": "Jornada de Trabalho", "content": "Art. 58. A duração normal do trabalho, para os empregados em qualquer atividade privada, não excederá de 8 (oito) horas diárias, desde que não seja fixado expressamente outro limite.\n\n§ 1º Não serão descontadas nem computadas como jornada extraordinária as variações de horário no registro de ponto não excedentes de cinco minutos.\n§ 2º O tempo despendido pelo empregado desde a sua residência até a efetiva ocupação do posto de trabalho e para o seu retorno não será computado na jornada de trabalho."},
            {"ref": "Art. 59", "title": "Horas Extras", "content": "Art. 59. A duração diária do trabalho poderá ser acrescida de horas extras, em número não excedente de duas, por acordo individual, convenção coletiva ou acordo coletivo de trabalho.\n\n§ 1º A remuneração da hora extra será, pelo menos, 50% (cinquenta por cento) superior à da hora normal.\n§ 2º Poderá ser dispensado o acréscimo de salário se, por força de acordo ou convenção coletiva de trabalho, o excesso de horas for compensado pela correspondente diminuição em outro dia.\n§ 5º O banco de horas poderá ser pactuado por acordo individual escrito, desde que a compensação ocorra no período máximo de seis meses."},
            {"ref": "Art. 130", "title": "Férias", "content": "Art. 130. Após cada período de 12 (doze) meses de vigência do contrato de trabalho, o empregado terá direito a férias, na seguinte proporção:\nI - 30 (trinta) dias corridos, quando não houver faltado ao serviço mais de 5 (cinco) vezes;\nII - 24 (vinte e quatro) dias corridos, quando houver tido de 6 (seis) a 14 (quatorze) faltas;\nIII - 18 (dezoito) dias corridos, quando houver tido de 15 (quinze) a 23 (vinte e três) faltas;\nIV - 12 (doze) dias corridos, quando houver tido de 24 (vinte e quatro) a 32 (trinta e duas) faltas."},
            {"ref": "Art. 443", "title": "Contrato de Trabalho", "content": "Art. 443. O contrato individual de trabalho poderá ser acordado tácita ou expressamente, verbalmente ou por escrito, por prazo determinado ou indeterminado, ou para prestação de trabalho intermitente.\n\n§ 1º Considera-se como de prazo determinado o contrato de trabalho cuja vigência dependa de termo prefixado ou da execução de serviços especificados ou ainda da realização de certo acontecimento suscetível de previsão aproximada.\n§ 3º Considera-se como intermitente o contrato de trabalho no qual a prestação de serviços, com subordinação, não é contínua, ocorrendo com alternância de períodos de prestação de serviços e de inatividade."},
            {"ref": "Art. 468", "title": "Alteração do Contrato", "content": "Art. 468. Nos contratos individuais de trabalho só é lícita a alteração das respectivas condições por mútuo consentimento, e ainda assim desde que não resultem, direta ou indiretamente, prejuízos ao empregado, sob pena de nulidade da cláusula infringente desta garantia.\n\n§ 1º Não se considera alteração unilateral a determinação do empregador para que o respectivo empregado reverta ao cargo efetivo, anteriormente ocupado, deixando o exercício de função de confiança.\n§ 2º A alteração de que trata o § 1º, com ou sem justo motivo, não assegura ao empregado o direito à manutenção do pagamento da gratificação correspondente."},
            {"ref": "Art. 477", "title": "Rescisão do Contrato", "content": "Art. 477. Na extinção do contrato de trabalho, o empregador deverá proceder à anotação na Carteira de Trabalho e Previdência Social, comunicar a dispensa aos órgãos competentes e realizar o pagamento das verbas rescisórias no prazo e na forma estabelecidos neste artigo.\n\n§ 2º O instrumento de rescisão ou recibo de quitação deverá especificar a natureza de cada parcela paga ao empregado e discriminar o seu valor.\n§ 6º A entrega ao empregado de documentos que comprovem a comunicação da extinção contratual aos órgãos competentes e o pagamento das verbas rescisórias deverão ser efetuados até dez dias contados a partir do término do contrato."},
        ],
    },
    {
        "title": "Marco Civil da Internet",
        "source": "Lei 12.965/2014",
        "category": "internet",
        "articles": [
            {"ref": "Art. 3º", "title": "Princípios", "content": "Art. 3º A disciplina do uso da internet no Brasil tem os seguintes princípios:\nI - garantia da liberdade de expressão, comunicação e manifestação de pensamento;\nII - proteção da privacidade;\nIII - proteção dos dados pessoais, na forma da lei;\nIV - preservação e garantia da neutralidade de rede;\nV - preservação da estabilidade, segurança e funcionalidade da rede;\nVI - responsabilização dos agentes de acordo com suas atividades;\nVII - preservação da natureza participativa da rede;\nVIII - liberdade dos modelos de negócios promovidos na internet."},
            {"ref": "Art. 7º", "title": "Direitos do Usuário", "content": "Art. 7º O acesso à internet é essencial ao exercício da cidadania, e ao usuário são assegurados os seguintes direitos:\nI - inviolabilidade da intimidade e da vida privada;\nII - inviolabilidade e sigilo do fluxo de suas comunicações pela internet;\nIII - inviolabilidade e sigilo de suas comunicações privadas armazenadas;\nIV - não suspensão da conexão à internet, salvo por débito;\nV - manutenção da qualidade contratada da conexão;\nVI - informações claras e completas constantes dos contratos de prestação de serviços;\nVII - não fornecimento a terceiros de seus dados pessoais sem consentimento livre, expresso e informado;\nVIII - informações claras e completas sobre coleta, uso, armazenamento, tratamento e proteção de seus dados pessoais;\nIX - consentimento expresso sobre coleta, uso, armazenamento e tratamento de dados pessoais;\nX - exclusão definitiva dos dados pessoais ao término da relação entre as partes;\nXI - publicidade e clareza de eventuais políticas de uso dos provedores de conexão à internet e de aplicações;\nXII - acessibilidade, consideradas as características físico-motoras, perceptivas, sensoriais, intelectuais e mentais do usuário;\nXIII - aplicação das normas de proteção e defesa do consumidor nas relações de consumo realizadas na internet."},
            {"ref": "Art. 9º", "title": "Neutralidade de Rede", "content": "Art. 9º O responsável pela transmissão, comutação ou roteamento tem o dever de tratar de forma isonômica quaisquer pacotes de dados, sem distinção por conteúdo, origem e destino, serviço, terminal ou aplicação.\n\n§ 1º A discriminação ou degradação do tráfego será regulamentada nos termos das atribuições privativas do Presidente da República.\n§ 2º Na hipótese de discriminação ou degradação do tráfego, o responsável deverá abster-se de causar dano aos usuários e explicar as práticas de gerenciamento de rede, informar previamente as práticas e oferecer serviços em condições comerciais não discriminatórias.\n§ 3º Na provisão de conexão à internet, onerosa ou gratuita, bem como na transmissão, comutação ou roteamento, é vedado bloquear, monitorar, filtrar ou analisar o conteúdo dos pacotes de dados."},
            {"ref": "Art. 10", "title": "Guarda de Registros", "content": "Art. 10. A guarda e a disponibilização dos registros de conexão e de acesso a aplicações de internet, bem como de dados pessoais e do conteúdo de comunicações privadas, devem atender à preservação da intimidade, da vida privada, da honra e da imagem das partes direta ou indiretamente envolvidas.\n\n§ 1º O provedor responsável pela guarda somente será obrigado a disponibilizar os registros mediante ordem judicial.\n§ 2º O conteúdo das comunicações privadas somente poderá ser disponibilizado mediante ordem judicial.\n§ 3º O disposto no caput não impede o acesso aos dados cadastrais que informem qualificação pessoal, filiação e endereço, na forma da lei."},
            {"ref": "Art. 13", "title": "Registros de Conexão", "content": "Art. 13. Na provisão de conexão à internet, cabe ao administrador de sistema autônomo respectivo o dever de manter os registros de conexão, sob sigilo, em ambiente controlado e de segurança, pelo prazo de 1 (um) ano, nos termos do regulamento.\n\n§ 1º A responsabilidade pela manutenção dos registros de conexão não poderá ser transferida a terceiros.\n§ 2º A autoridade policial ou administrativa ou o Ministério Público poderá requerer cautelarmente que os registros de conexão sejam guardados por prazo superior."},
            {"ref": "Art. 15", "title": "Registros de Acesso a Aplicações", "content": "Art. 15. O provedor de aplicações de internet constituído na forma de pessoa jurídica e que exerça essa atividade de forma organizada, profissionalmente e com fins econômicos deverá manter os respectivos registros de acesso a aplicações de internet, sob sigilo, em ambiente controlado e de segurança, pelo prazo de 6 (seis) meses.\n\n§ 1º Ordem judicial poderá obrigar, por tempo certo, os provedores de aplicações de internet que não estão sujeitos ao disposto no caput a guardarem registros de acesso.\n§ 2º A autoridade policial ou administrativa ou o Ministério Público poderão requerer cautelarmente a qualquer provedor de aplicações de internet que os registros de acesso a aplicações de internet sejam guardados."},
            {"ref": "Art. 19", "title": "Responsabilidade por Conteúdo de Terceiros", "content": "Art. 19. Com o intuito de assegurar a liberdade de expressão e impedir a censura, o provedor de aplicações de internet somente poderá ser responsabilizado civilmente por danos decorrentes de conteúdo gerado por terceiros se, após ordem judicial específica, não tomar as providências para, no âmbito e nos limites técnicos do seu serviço e dentro do prazo assinalado, tornar indisponível o conteúdo apontado como infringente, ressalvadas as disposições legais em contrário."},
        ],
    },
    {
        "title": "Lei Anticorrupção",
        "source": "Lei 12.846/2013",
        "category": "anticorrupção",
        "articles": [
            {"ref": "Art. 1º", "title": "Objeto da Lei", "content": "Art. 1º Esta Lei dispõe sobre a responsabilização objetiva administrativa e civil de pessoas jurídicas pela prática de atos contra a administração pública, nacional ou estrangeira."},
            {"ref": "Art. 2º", "title": "Aplicação", "content": "Art. 2º As pessoas jurídicas serão responsabilizadas objetivamente, nos âmbitos administrativo e civil, pelos atos lesivos previstos nesta Lei praticados em seu interesse ou benefício, exclusivo ou não."},
            {"ref": "Art. 5º", "title": "Atos Lesivos", "content": "Art. 5º Constituem atos lesivos à administração pública, nacional ou estrangeira:\nI - prometer, oferecer ou dar, direta ou indiretamente, vantagem indevida a agente público;\nII - comprovadamente, financiar, custear, patrocinar ou de qualquer modo subvencionar a prática dos atos ilícitos previstos nesta Lei;\nIII - comprovadamente, utilizar-se de interposta pessoa física ou jurídica para ocultar ou dissimular seus reais interesses ou a identidade dos beneficiários;\nIV - no tocante a licitações e contratos:\na) frustrar ou fraudar o caráter competitivo de procedimento licitatório;\nb) impedir, perturbar ou fraudar a realização de qualquer ato;\nc) afastar ou procurar afastar licitante;\nd) fraudar licitação pública ou contrato;\ne) criar, de modo fraudulento ou irregular, pessoa jurídica para participar de licitação;\nV - dificultar atividade de investigação ou fiscalização de órgãos."},
            {"ref": "Art. 6º", "title": "Sanções Administrativas", "content": "Art. 6º Na esfera administrativa, serão aplicadas às pessoas jurídicas consideradas responsáveis pelos atos lesivos previstos nesta Lei as seguintes sanções:\nI - multa, no valor de 0,1% (um décimo por cento) a 20% (vinte por cento) do faturamento bruto do último exercício anterior ao da instauração do processo administrativo, excluídos os tributos, a qual nunca será inferior à vantagem auferida;\nII - publicação extraordinária da decisão condenatória.\n\n§ 1º As sanções serão aplicadas fundamentadamente, isolada ou cumulativamente.\n§ 4º Caso não seja possível utilizar o critério do valor do faturamento bruto, a multa será de R$ 6.000,00 (seis mil reais) a R$ 60.000.000,00 (sessenta milhões de reais)."},
            {"ref": "Art. 7º", "title": "Parâmetros das Sanções", "content": "Art. 7º Serão levados em consideração na aplicação das sanções:\nI - a gravidade da infração;\nII - a vantagem auferida ou pretendida pelo infrator;\nIII - a consumação ou não da infração;\nIV - o grau de lesão ou perigo de lesão;\nV - o efeito negativo produzido pela infração;\nVI - a situação econômica do infrator;\nVII - a cooperação da pessoa jurídica para a apuração das infrações;\nVIII - a existência de mecanismos e procedimentos internos de integridade, auditoria e incentivo à denúncia e à aplicação efetiva de códigos de ética e de conduta;\nIX - o valor dos contratos mantidos pela pessoa jurídica com o órgão ou entidade pública lesados."},
            {"ref": "Art. 16", "title": "Acordo de Leniência", "content": "Art. 16. A autoridade máxima de cada órgão ou entidade pública poderá celebrar acordo de leniência com as pessoas jurídicas responsáveis pela prática dos atos previstos nesta Lei que colaborem efetivamente com as investigações e o processo administrativo, sendo que dessa colaboração resulte:\nI - a identificação dos demais envolvidos na infração, quando couber;\nII - a obtenção célere de informações e documentos que comprovem o ilícito sob apuração.\n\n§ 1º O acordo somente poderá ser celebrado se preenchidos, cumulativamente, os seguintes requisitos:\nI - a pessoa jurídica seja a primeira a se manifestar sobre seu interesse em cooperar para a apuração do ato ilícito;\nII - a pessoa jurídica cesse completamente seu envolvimento na infração investigada;\nIII - a pessoa jurídica admita sua participação no ilícito e coopere plena e permanentemente com as investigações."},
        ],
    },
    {
        "title": "Nova Lei de Licitações e Contratos Administrativos",
        "source": "Lei 14.133/2021",
        "category": "licitações",
        "articles": [
            {"ref": "Art. 1º", "title": "Objeto da Lei", "content": "Art. 1º Esta Lei estabelece normas gerais de licitação e contratação para as Administrações Públicas diretas, autárquicas e fundacionais da União, dos Estados, do Distrito Federal e dos Municípios."},
            {"ref": "Art. 5º", "title": "Princípios", "content": "Art. 5º Na aplicação desta Lei, serão observados os princípios da legalidade, da impessoalidade, da moralidade, da publicidade, da eficiência, do interesse público, da probidade administrativa, da igualdade, do planejamento, da transparência, da eficácia, da segregação de funções, da motivação, da vinculação ao edital, do julgamento objetivo, da segurança jurídica, da razoabilidade, da competitividade, da proporcionalidade, da celeridade, da economicidade e do desenvolvimento nacional sustentável."},
            {"ref": "Art. 25", "title": "Contratação Direta", "content": "Art. 25. É inexigível a licitação quando inviável a competição, em especial nos casos de:\nI - aquisição de materiais, de equipamentos ou de gêneros ou contratação de serviços que só possam ser fornecidos por produtor, empresa ou representante comercial exclusivos;\nII - contratação de profissional do setor artístico;\nIII - contratação dos seguintes serviços técnicos especializados de natureza predominantemente intelectual;\nIV - objetos que devam ou possam ser contratados por meio de credenciamento;\nV - aquisição ou locação de imóvel cujas características de instalações e de localização tornem necessária sua escolha."},
            {"ref": "Art. 72", "title": "Modalidades de Licitação", "content": "Art. 72. O processo de licitação observará as seguintes fases, em sequência:\nI - preparatória;\nII - de divulgação do edital de licitação;\nIII - de apresentação de propostas e lances;\nIV - de julgamento;\nV - de habilitação;\nVI - recursal;\nVII - de homologação."},
            {"ref": "Art. 155", "title": "Sanções ao Licitante", "content": "Art. 155. O licitante ou o contratado será responsabilizado administrativamente pelas seguintes infrações:\nI - dar causa à inexecução parcial do contrato;\nII - dar causa à inexecução parcial do contrato que cause grave dano à Administração;\nIII - dar causa à inexecução total do contrato;\nIV - deixar de entregar a documentação exigida para o certame;\nV - não manter a proposta, salvo em decorrência de fato superveniente devidamente justificado;\nVI - não celebrar o contrato ou não entregar a documentação exigida;\nVII - ensejar o retardamento da execução ou da entrega do objeto da licitação;\nVIII - apresentar declaração ou documentação falsa ou prestar declaração falsa;\nIX - fraudar a licitação ou praticar ato fraudulento na execução do contrato;\nX - comportar-se de modo inidôneo ou cometer fraude de qualquer natureza;\nXI - praticar atos ilícitos com vistas a frustrar os objetivos da licitação;\nXII - praticar ato lesivo previsto no art. 5º da Lei nº 12.846, de 1º de agosto de 2013."},
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# SEED FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt_embedding(emb):
    """Format embedding list as pgvector-compatible string: '[0.1,0.2,...]'"""
    if not emb:
        return None
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def seed_legal_base(engine):
    """
    Seed the legal database with proper structure:
    - 1 legal_document per law
    - N legal_chunks per law (one per article)

    Idempotent: skips laws that already have chunks.
    After seeding, backfills embeddings for any chunks missing them.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "legal_documents" not in tables or "legal_chunks" not in tables:
        print("❌ Tables legal_documents/legal_chunks don't exist yet.")
        return False

    total_docs = 0
    total_chunks = 0

    with Session(engine) as session:
        for law in LAWS:
            # Check if this law already has chunks (proper structure)
            existing = session.execute(
                text("""
                    SELECT ld.id, COUNT(lc.id) as chunk_count
                    FROM legal_documents ld
                    LEFT JOIN legal_chunks lc ON lc.document_id = ld.id
                    WHERE ld.source = :source
                    GROUP BY ld.id
                    HAVING COUNT(lc.id) > 0
                    LIMIT 1
                """),
                {"source": law["source"]},
            ).fetchone()

            if existing:
                print(f"  ⏭  {law['source']} já tem {existing.chunk_count} chunks, pulando...")
                continue

            # Delete any old orphan documents (from old seeds that had no chunks)
            session.execute(
                text("""
                    DELETE FROM legal_documents
                    WHERE (source = :source OR source LIKE :source_pattern)
                    AND id NOT IN (SELECT DISTINCT document_id FROM legal_chunks WHERE document_id IS NOT NULL)
                """),
                {"source": law["source"], "source_pattern": f"%{law['source']}%"},
            )

            # Create the parent document
            doc_id = str(uuid.uuid4())
            full_text = "\n\n".join(
                f"{a['ref']} - {a['title']}\n{a['content']}" for a in law["articles"]
            )
            now = datetime.now(timezone.utc)

            session.execute(
                text("""
                    INSERT INTO legal_documents (id, title, source, category, full_text, created_at)
                    VALUES (:id, :title, :source, :category, :full_text, :created_at)
                """),
                {
                    "id": doc_id,
                    "title": law["title"],
                    "source": law["source"],
                    "category": law["category"],
                    "full_text": full_text,
                    "created_at": now,
                },
            )
            total_docs += 1

            # Create chunks (one per article) — WITHOUT embeddings first
            for idx, article in enumerate(law["articles"]):
                chunk_id = str(uuid.uuid4())
                session.execute(
                    text("""
                        INSERT INTO legal_chunks (id, document_id, chunk_index, content, article_ref, metadata)
                        VALUES (:id, :document_id, :chunk_index, :content, :article_ref, :metadata)
                    """),
                    {
                        "id": chunk_id,
                        "document_id": doc_id,
                        "chunk_index": idx,
                        "content": article["content"],
                        "article_ref": article["ref"],
                        "metadata": "{}",
                    },
                )
                total_chunks += 1

            print(f"  ✅ {law['title']} — {len(law['articles'])} artigos")

        session.commit()

    print(f"\n📊 Seed concluído: {total_docs} leis, {total_chunks} artigos inseridos")

    # ── Backfill embeddings for ALL chunks that don't have them ──
    _backfill_embeddings(engine)

    return True


def _backfill_embeddings(engine):
    """Generate embeddings for all legal_chunks where embedding IS NULL."""
    try:
        from app.services.embedding_service import generate_embeddings_batch
    except Exception as e:
        print(f"\n⚠️  Não foi possível importar embedding_service: {e}")
        return

    with Session(engine) as session:
        # Get all chunks without embeddings
        rows = session.execute(
            text("SELECT id, content FROM legal_chunks WHERE embedding IS NULL ORDER BY chunk_index")
        ).fetchall()

        if not rows:
            print("\n✨ Todos os chunks já possuem embeddings.")
            return

        print(f"\n🔄 Gerando embeddings para {len(rows)} chunks via OpenAI...")

        # Process in batches
        batch_size = 50
        updated = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            texts = [r.content for r in batch]
            ids = [str(r.id) for r in batch]

            try:
                embeddings = generate_embeddings_batch(texts)

                for chunk_id, emb in zip(ids, embeddings):
                    emb_str = _fmt_embedding(emb)
                    session.execute(
                        text("UPDATE legal_chunks SET embedding = CAST(:emb AS vector) WHERE id = CAST(:id AS uuid)"),
                        {"emb": emb_str, "id": chunk_id},
                    )
                    updated += 1

                session.commit()
                print(f"  ✅ Batch {i // batch_size + 1}: {len(batch)} embeddings gerados")

            except Exception as e:
                print(f"  ❌ Erro no batch {i // batch_size + 1}: {e}")
                session.rollback()
                break

        print(f"\n📊 Embeddings: {updated}/{len(rows)} chunks atualizados")


if __name__ == "__main__":
    engine = get_sync_engine()
    print("🏛️  Seed da Base Legal Consolidada")
    print("=" * 50)
    seed_legal_base(engine)
    engine.dispose()
