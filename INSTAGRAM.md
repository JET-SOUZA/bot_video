# Instagram no JetBot

Stories precisam de uma sessão válida com acesso ao conteúdo. Configure na
hospedagem `COOKIES_IG_B64`: base64 de um arquivo de cookies no formato
Mozilla/Netscape exportado de uma sessão sua do Instagram. A alternativa
`COOKIES_INSTAGRAM` recebe o texto do arquivo sem base64. Não use cookies do
YouTube nessa variável. Não publique cookies no GitHub nem em mensagens do bot.

O bot verifica se há um `sessionid` do Instagram não expirado antes de consultar
Stories. Isso não verifica se a sessão foi revogada pelo Instagram: nesse caso,
renove-a após entrar normalmente no site. A sessão não concede acesso a Stories
expirados ou a conteúdo que a conta não consegue visualizar.

Os downloads do Instagram não executam mais o fallback legado, que repetia a
mesma extração. Há uma tentativa por solicitação, sem retries automáticos, com
intervalo de dois segundos entre consultas de metadados. Uma solicitação pode
precisar de várias consultas. Apenas um download do Instagram roda por vez.

Ao receber HTTP 429, o processo pausa novas solicitações do Instagram por
15 minutos. A pausa usa relógio monotônico e é local ao processo (uma réplica);
reinícios a apagam. O prazo é uma espera conservadora do bot, não uma promessa
de liberação do Instagram. Sessão válida e redução de requisições não garantem
que a plataforma aceite downloads a partir da hospedagem.
