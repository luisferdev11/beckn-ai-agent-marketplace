USER_PROMPT = """Acabo de recibir este review de un cliente sobre nuestro software. Necesito
un análisis completo para el equipo de producto:

- qué tan negativo es y por qué
- los hechos concretos que menciona (bugs, tiempos, precios, etc.)
- en qué categoría de problema cae para enrutarlo al equipo correcto
- una evaluación con sugerencias accionables para mejorar el producto
- una versión condensada en inglés para enviar al equipo internacional

REVIEW:
Llevo 3 meses usando este software y honestamente es frustrante. La app
se cuelga al menos 2 veces al día, la interfaz es confusa y el soporte
técnico tarda 48 horas en responder. Pagué $80 al mes esperando algo mejor."""

PLAN = """Goal: procesar una reseña negativa (traducir, analizar sentimiento, clasificar queja, generar preguntas).

4 steps en 2 capas de ejecución:

Layer 1 (paralelo): step1 (translator) · step2 (sentiment) · step3 (classifier) — los tres se disparan al mismo tiempo, no se dependen.
Layer 2 (secuencial): step4 (questioner) — espera a step1 porque genera las preguntas sobre la traducción."""