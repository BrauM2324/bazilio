import os
import re
import shutil
import subprocess
import sys
import threading

from antlr4 import CommonTokenStream, FileStream
from antlr4.error.ErrorListener import ErrorListener

from BazilioLexer import BazilioLexer
from BazilioParser import BazilioParser
from BazilioVisitor import BazilioVisitor


# ETAPA 1: análisis sintáctico con el lexer y el parser generados desde Bazilio.g4.
class ErrorBazilio(Exception):
	"""Error de sintaxis o de ejecución de un programa Bazilio."""


class _ListenerErrores(ErrorListener):
	def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
		raise ErrorBazilio(
			f"Error de sintaxis en la línea {line}, columna {column}: {msg}")


def parsear(flujo):
	lexer = BazilioLexer(flujo)
	lexer.removeErrorListeners()
	lexer.addErrorListener(_ListenerErrores())
	parser = BazilioParser(CommonTokenStream(lexer))
	parser.removeErrorListeners()
	parser.addErrorListener(_ListenerErrores())
	return parser.programa()


# ETAPA 2: operaciones aritméticas con división entera compatible con C.
def _div_c(a, b):
	"""División entera con truncamiento hacia cero, como en C."""
	cociente = abs(a) // abs(b)
	return cociente if (a < 0) == (b < 0) else -cociente


NOTA_MIN, NOTA_MAX = 0, 51
_POSICION = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}


def valor_nota(texto):
	"""Convierte nombres de notas de piano en valores enteros de 0 a 51."""
	letra = texto[0]
	octava = int(texto[1]) if len(texto) == 2 else 4
	if octava == 0:
		if letra not in "AB":
			raise ErrorBazilio(f"La nota {texto} no existe en el piano "
							   "(la octava 0 solo tiene A0 y B0).")
		return 0 if letra == "A" else 1
	valor = 2 + 7 * (octava - 1) + _POSICION[letra]
	if valor > NOTA_MAX:
		raise ErrorBazilio(
			f"La nota {texto} no existe en el piano (la última es C8).")
	return valor


class Interprete(BazilioVisitor):
	# ETAPA 2: estado, variables, entrada/salida y evaluación de expresiones básicas.
	def __init__(self, entrada=None, salida=None):
		self.procedimientos = {}
		self.marcos = []
		self._entrada = entrada if entrada is not None else sys.stdin
		self._tokens_entrada = []
		self._salida = salida if salida is not None else print
		self.partitura = []

	@property
	def _vars(self):
		return self.marcos[-1]

	# ETAPA 4: registro de procedimientos y gestión de marcos para cada llamada.
	def cargar(self, arbol):
		for procedimiento in arbol.procedimiento():
			nombre = procedimiento.PROC_ID().getText()
			parametros = [variable.getText() for variable in procedimiento.VAR()]
			if nombre in self.procedimientos:
				raise ErrorBazilio(
					f"El procedimiento {nombre} está definido más de una vez.")
			if len(set(parametros)) != len(parametros):
				raise ErrorBazilio(f"El procedimiento {nombre} repite nombres "
								   "de parámetros formales.")
			self.procedimientos[nombre] = (parametros, procedimiento.bloque())

	def ejecutar(self, inicio="Main"):
		self._llamar(inicio, [])

	def _llamar(self, nombre, valores):
		if nombre not in self.procedimientos:
			raise ErrorBazilio(
				f"Se llamó al procedimiento {nombre}, que no está definido.")
		parametros, bloque = self.procedimientos[nombre]
		if len(parametros) != len(valores):
			raise ErrorBazilio(f"{nombre} espera {len(parametros)} parámetro(s) "
							   f"y recibió {len(valores)}.")
		self.marcos.append(dict(zip(parametros, valores)))
		try:
			self.visit(bloque)
		finally:
			self.marcos.pop()

	# ETAPA 2: ejecución de bloques, asignación, lectura y escritura.
	def visitBloque(self, ctx):
		for instruccion in ctx.instruccion():
			self.visit(instruccion)

	# ETAPA 5: al asignar una lista se copia para evitar alias entre variables.
	def visitAsignacion(self, ctx):
		valor = self.visit(ctx.expr())
		if isinstance(valor, list):
			valor = list(valor)
		self._vars[ctx.VAR().getText()] = valor

	def visitLectura(self, ctx):
		self._vars[ctx.VAR().getText()] = self._leer_entero()

	def visitEscritura(self, ctx):
		partes = []
		for hijo in list(ctx.getChildren())[1:]:
			if hasattr(hijo, "symbol"):
				partes.append(hijo.getText()[1:-1])
			else:
				partes.append(self._formatear(self.visit(hijo)))
		self._salida(" ".join(partes))

	# ETAPA 6: la instrucción de reproducción acumula las notas para la partitura.
	def visitReproduccion(self, ctx):
		valor = self.visit(ctx.expr())
		for nota in valor if isinstance(valor, list) else [valor]:
			nota_a_lilypond(self._entero(nota))
			self.partitura.append(nota)

	# ETAPA 4: llamadas a procedimientos, incluidos los casos recursivos.
	def visitInvocacion(self, ctx):
		valores = [self.visit(expr) for expr in ctx.expr()]
		self._llamar(ctx.PROC_ID().getText(), valores)

	# ETAPA 3: selección de ramas y repetición mediante if/else y while.
	def visitCondicional(self, ctx):
		bloques = ctx.bloque()
		if self._verdadero(self.visit(ctx.expr())):
			self.visit(bloques[0])
		elif len(bloques) > 1:
			self.visit(bloques[1])

	def visitIteracion(self, ctx):
		while self._verdadero(self.visit(ctx.expr())):
			self.visit(ctx.bloque())

	# ETAPA 5: mutación de listas mediante agregado y eliminación por índice.
	def visitAgregado(self, ctx):
		nombre = ctx.VAR().getText()
		lista = self._vars.get(nombre, 0)
		if not isinstance(lista, list):
			raise ErrorBazilio(f"{nombre} no es una lista: "
							   "no se puede usar << con ella.")
		valor = self.visit(ctx.expr())
		if isinstance(valor, list):
			raise ErrorBazilio("Las listas solo pueden contener enteros o notas.")
		lista.append(valor)

	def visitCorte(self, ctx):
		nombre = ctx.VAR().getText()
		lista = self._vars.get(nombre, 0)
		if not isinstance(lista, list):
			raise ErrorBazilio(f"{nombre} no es una lista: "
							   "no se puede usar 8< con ella.")
		indice = self._entero(self.visit(ctx.expr()))
		self._comprobar_indice(nombre, lista, indice)
		del lista[indice - 1]

	# ETAPA 2: valores enteros, variables y evaluación de operadores.
	def visitEntero(self, ctx):
		return int(ctx.getText())

	def visitVariable(self, ctx):
		return self._vars.get(ctx.getText(), 0)

	def visitParentesis(self, ctx):
		return self.visit(ctx.expr())

	# ETAPA 5: notas como valores numéricos y operaciones con listas.
	def visitNota(self, ctx):
		return valor_nota(ctx.getText())

	def visitLista(self, ctx):
		elementos = [self.visit(expr) for expr in ctx.expr()]
		if any(isinstance(elemento, list) for elemento in elementos):
			raise ErrorBazilio("Las listas solo pueden contener enteros o notas.")
		return elementos

	def visitLongitud(self, ctx):
		valor = self.visit(ctx.expr())
		if not isinstance(valor, list):
			raise ErrorBazilio("El operador # solo se puede aplicar a una lista.")
		return len(valor)

	def visitIndice(self, ctx):
		base = self.visit(ctx.expr(0))
		if not isinstance(base, list):
			raise ErrorBazilio("Solo se puede consultar un índice en una lista.")
		indice = self._entero(self.visit(ctx.expr(1)))
		self._comprobar_indice(ctx.expr(0).getText(), base, indice)
		return base[indice - 1]

	def visitMulDiv(self, ctx):
		izquierda, derecha = self._operandos(ctx)
		operador = ctx.op.text
		if operador == "*":
			return izquierda * derecha
		if derecha == 0:
			raise ErrorBazilio("División por cero.")
		cociente = _div_c(izquierda, derecha)
		return cociente if operador == "/" else izquierda - derecha * cociente

	def visitSumaResta(self, ctx):
		izquierda, derecha = self._operandos(ctx)
		return izquierda + derecha if ctx.op.text == "+" else izquierda - derecha

	def visitRelacional(self, ctx):
		izquierda, derecha = self._operandos(ctx)
		comparaciones = {
			"<": izquierda < derecha,
			">": izquierda > derecha,
			"<=": izquierda <= derecha,
			">=": izquierda >= derecha,
		}
		return int(comparaciones[ctx.op.text])

	def visitIgualdad(self, ctx):
		izquierda = self.visit(ctx.expr(0))
		derecha = self.visit(ctx.expr(1))
		return int((izquierda == derecha) if ctx.op.text == "="
				   else (izquierda != derecha))

	# ETAPA 5: notas, listas, longitudes, índices y validación de tipos/índices.
	@staticmethod
	def _entero(valor):
		if isinstance(valor, list):
			raise ErrorBazilio("Se esperaba un entero y se encontró una lista.")
		return valor

	def _operandos(self, ctx):
		izquierda = self._entero(self.visit(ctx.expr(0)))
		derecha = self._entero(self.visit(ctx.expr(1)))
		return izquierda, derecha

	@staticmethod
	def _verdadero(valor):
		if isinstance(valor, list):
			raise ErrorBazilio("Una condición debe ser un entero "
							   "(0 es falso, otro valor es verdadero).")
		return valor != 0

	@staticmethod
	def _formatear(valor):
		if isinstance(valor, list):
			return "[" + " ".join(str(elemento) for elemento in valor) + "]"
		return str(valor)

	def _leer_entero(self):
		while not self._tokens_entrada:
			linea = self._entrada.readline()
			if linea == "":
				raise ErrorBazilio(
					"Se esperaba un entero en la entrada, pero ya no hay más datos.")
			self._tokens_entrada = linea.split()
		token = self._tokens_entrada.pop(0)
		try:
			return int(token)
		except ValueError:
			raise ErrorBazilio(
				f"Se esperaba un entero en la entrada y se leyó «{token}».")

	@staticmethod
	def _comprobar_indice(nombre, lista, indice):
		cantidad = len(lista)
		if not 1 <= indice <= cantidad:
			raise ErrorBazilio(
				f"Índice {indice} inexistente en {nombre} (la lista tiene "
				f"{cantidad} elemento(s); los índices van de 1 a {cantidad}).")


# ETAPA 5: conversión de notas y ETAPA 6: salida de LilyPond y formatos de audio.
def nota_a_lilypond(valor):
	"""Convierte un valor de piano en una nota absoluta de LilyPond."""
	if not NOTA_MIN <= valor <= NOTA_MAX:
		raise ErrorBazilio(
			f"Se intentó tocar el valor {valor}, fuera del rango del piano (0 a 51).")
	if valor < 2:
		letra, octava = ("a", "b")[valor], 0
	else:
		indice = valor - 2
		octava, letra = 1 + indice // 7, "cdefgab"[indice % 7]
	marcas = "'" * (octava - 3) if octava > 3 else "," * (3 - octava)
	return f"{letra}{marcas}4"


def version_lilypond():
	try:
		salida = subprocess.run(["lilypond", "--version"],
								capture_output=True, text=True).stdout
		coincidencia = re.search(r"(\d+\.\d+\.\d+)", salida)
		return coincidencia.group(1) if coincidencia else "2.20.0"
	except OSError:
		return "2.20.0"


def texto_lilypond(partitura, tempo=120):
	notas = [nota_a_lilypond(valor) for valor in partitura]
	renglones = [" ".join(notas[indice:indice + 8])
				 for indice in range(0, len(notas), 8)]
	cuerpo = "\n".join("      " + renglon for renglon in renglones)
	return (f'\\version "{version_lilypond()}"\n'
			"\\score {\n"
			"  \\absolute {\n"
			f"    \\tempo 4 = {tempo}\n"
			f"{cuerpo}\n"
			"  }\n"
			"  \\layout { }\n"
			"  \\midi { }\n"
			"}\n")


def generar_salida(partitura, base, solo_ly=False, aviso=print):
	"""Escribe el archivo LilyPond y genera los formatos disponibles."""
	ruta_ly = base + ".ly"
	with open(ruta_ly, "w", encoding="utf-8") as archivo:
		archivo.write(texto_lilypond(partitura))
	generados = [ruta_ly]
	if solo_ly:
		return generados

	def correr(comando, descripcion):
		if shutil.which(comando[0]) is None:
			aviso(f"Aviso: no se encontró «{comando[0]}», "
				  f"no se generó {descripcion}.")
			return False
		resultado = subprocess.run(comando, capture_output=True, text=True)
		if resultado.returncode != 0:
			detalle = resultado.stderr.strip()[-400:]
			aviso(f"Aviso: falló {comando[0]} al generar {descripcion}:\n{detalle}")
			return False
		return True

	pasos = [
		(["lilypond", "-o", base, ruta_ly], "el PDF y el MIDI", [".pdf", ".midi"]),
		(["timidity", "-A", "100,100", "-Ow", "-o", base + ".wav", base + ".midi"],
		 "el WAV", [".wav"]),
		(["ffmpeg", "-y", "-loglevel", "error", "-i", base + ".wav",
		  "-af", "loudnorm=I=-10:TP=-1.0:LRA=7", "-c:a", "pcm_s16le",
		  base + ".normalized.wav"],
		 "la normalización del WAV", [".normalized.wav"]),
		(["ffmpeg", "-y", "-loglevel", "error", "-i", base + ".wav",
		  "-codec:a", "libmp3lame", "-qscale:a", "2", base + ".mp3"],
		 "el MP3", [".mp3"]),
	]
	for comando, descripcion, extensiones in pasos:
		if not correr(comando, descripcion):
			break
		if descripcion == "la normalización del WAV":
			os.replace(base + ".normalized.wav", base + ".wav")
			continue
		generados.extend(base + extension for extension in extensiones)
	return generados


def principal(argv):
	solo_ly = "--solo-ly" in argv
	argumentos = [arg for arg in argv[1:] if not arg.startswith("--")]
	if not argumentos:
		print("Uso: python3 bazilio.py programa.bzl [Procedimiento] [--solo-ly]")
		return 2
	ruta = argumentos[0]
	inicio = argumentos[1] if len(argumentos) > 1 else "Main"
	try:
		arbol = parsear(FileStream(ruta, encoding="utf-8"))
		interprete = Interprete()
		interprete.cargar(arbol)
		interprete.ejecutar(inicio)
		if interprete.partitura:
			base = os.path.splitext(ruta)[0]
			archivos = generar_salida(interprete.partitura, base, solo_ly=solo_ly)
			nombres = ", ".join(os.path.basename(archivo) for archivo in archivos)
			print("Archivos generados: " + nombres, file=sys.stderr)
	except ErrorBazilio as error:
		print(f"Error: {error}", file=sys.stderr)
		return 1
	except BrokenPipeError:
		return 0
	return 0


# ETAPA 6: amplía la pila disponible para ejecutar recursiones musicales profundas.
if __name__ == "__main__":
	sys.setrecursionlimit(200000)
	threading.stack_size(512 * 1024 * 1024)
	resultado = []
	hilo = threading.Thread(target=lambda: resultado.append(principal(sys.argv)))
	hilo.start()
	hilo.join()
	sys.exit(resultado[0] if resultado else 1)
