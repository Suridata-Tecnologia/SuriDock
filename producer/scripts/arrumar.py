def connection_rabbitmq():
    credentials = pika.PlainCredentials(
        username=RABBITMQ_USERNAME,
        password=RABBITMQ_PASSWORD
    )

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=5672,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=600,
        )
    )

    channel = connection.channel()
    return connection, channel


def get_queue():
    connection, channel = connection_rabbitmq()

    mensagens = []
    buffer_mensagens = []  # (body, properties) para re-publicar

    # 1. Ler tudo da fila
    while True:
        method, properties, body = channel.basic_get(queue=RABBITMQ_QUEUE, auto_ack=False)
        if method is None:
            # não tem nada no rabbitmq
            break

        mensagens.append(body.decode())
        buffer_mensagens.append((body, properties))

        # ACK para remover temporariamente
        channel.basic_ack(method.delivery_tag)

    # 2. Restaurar a fila na ordem certa
    for body, props in buffer_mensagens:
        channel.basic_publish(
            exchange='',
            routing_key=RABBITMQ_QUEUE,
            body=body,
            properties=props
        )

    connection.close()
    return mensagens