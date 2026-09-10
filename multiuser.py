from sniper_deals import Product, apply_filters


HELP = ("Comandos: /status, /ultimos, /pausar, /retomar, /parar, "
        "/incluir palavras, /excluir palavras, /precomax valor, /plataformas lista")


class MultiUserBot:
    def __init__(self, store, invite_code: str, admin_chat_id: str, sender, health_provider=None):
        self.store = store
        self.invite_code = invite_code
        self.admin_chat_id = str(admin_chat_id)
        self.sender = sender
        self.health_provider = health_provider or (lambda: {})

    def command(self, chat_id: str, name: str, text: str, chat_type: str = "private") -> str:
        chat_id = str(chat_id)
        command, _, argument = text.strip().partition(" ")
        command = command.lower().split("@", 1)[0]
        if chat_type != "private" and command != "/status":
            return "Por segurança, use este bot apenas em chat privado."
        if command == "/start":
            if not self.invite_code or argument.strip() != self.invite_code:
                return "Código de convite inválido. Peça um convite ao administrador."
            if not self.store.register(chat_id, name):
                return "Usuário bloqueado."
            return f"✅ {name or 'Usuário'} cadastrado. {HELP}"

        if command in ("/usuarios", "/bloquear", "/broadcast", "/saude"):
            if chat_id != self.admin_chat_id:
                return "Comando restrito ao administrador."
            if command == "/usuarios":
                users = self.store.active_users()
                return "👥 Usuários ativos\n" + ("\n".join(
                    f"{user['name'] or 'Sem nome'} — {user['chat_id']}" for user in users) or "Nenhum")
            if command == "/saude":
                state = self.health_provider()
                return ("📊 Status do monitor\n"
                        f"Falhas consecutivas: {state.get('failure_count', 0)}\n"
                        f"Último sucesso: {state.get('last_success') or 'nunca'}\n"
                        f"Última falha: {state.get('last_failure') or 'nenhuma'}")
            if command == "/bloquear":
                if not self.store.ban(argument.strip()):
                    return "Usuário não encontrado."
                return f"🚫 Usuário {argument.strip()} bloqueado."
            if not argument.strip():
                return "Use /broadcast mensagem"
            users = self.store.active_users()
            for user in users:
                self.sender((user["chat_id"], argument.strip()))
            return f"📣 Broadcast enviado para {len(users)} usuário(s)."

        user = self.store.get(chat_id)
        if not user or not user["active"]:
            return "Você não está cadastrado. Use /start CODIGO-DE-CONVITE."
        if command == "/parar":
            self.store.unsubscribe(chat_id)
            return "Inscrição removida. Você não receberá mais alertas."
        if command == "/pausar":
            self.store.set_paused(chat_id, True)
            return "⏸️ Alertas pausados."
        if command == "/retomar":
            self.store.set_paused(chat_id, False)
            return "▶️ Alertas retomados."
        if command == "/incluir":
            self.store.update(chat_id, include=argument.strip())
            return f"✅ Inclusão: {argument.strip() or 'desativada'}"
        if command == "/excluir":
            self.store.update(chat_id, exclude=argument.strip())
            return f"✅ Exclusão: {argument.strip() or 'desativada'}"
        if command == "/precomax":
            if argument.strip():
                float(argument.strip())
            self.store.update(chat_id, max_price=argument.strip())
            return f"✅ Preço máximo: {argument.strip() or 'desativado'}"
        if command == "/plataformas":
            self.store.update(chat_id, platforms=argument.strip())
            return f"✅ Plataformas: {argument.strip() or 'todas'}"
        if command == "/status":
            return ("✅ Assinatura ativa\n"
                    f"Inclusão: {user['include'] or 'tudo'}\n"
                    f"Exclusão: {user['exclude'] or 'nenhuma'}\n"
                    f"Preço máximo: {user['max_price'] or 'sem limite'}\n"
                    f"Plataformas: {user['platforms'] or 'todas'}")
        if command == "/ultimos":
            deliveries = self.store.recent_deliveries(chat_id)
            if not deliveries:
                return "Nenhum item enviado para você ainda."
            return "🕘 Seus últimos itens\n\n" + "\n\n".join(
                f"📦 {item['title'] or item['product_id']}\n"
                f"💴 ¥{item['price']}\n🔗 {item['url']}"
                for item in deliveries)
        return HELP

    def deliver(self, product: Product, allow_new: bool = True) -> int:
        sent = 0
        for user in self.store.active_users():
            if not apply_filters([product], user["include"], user["exclude"],
                                 user["max_price"], user["platforms"]):
                continue
            old_price = self.store.last_price(user["chat_id"], product.id)
            if old_price is None and allow_new:
                self.sender((user["chat_id"], product, False, None))
            elif old_price is not None and float(product.price) < float(old_price):
                self.sender((user["chat_id"], product, True, old_price))
            else:
                continue
            self.store.mark_sent(user["chat_id"], product.id, product.price,
                                 title=product.title, url=product.url)
            sent += 1
        return sent
