from dataclasses import dataclass, field
import re
import typing as t
from pathlib import Path


def preprocess(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return " "  # note: a space and not an empty string
        else:
            return s

    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE,
    )
    return re.sub(pattern, replacer, text)


def camel_to_snake(name):
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()


def snake_to_camel(name):
    return ''.join(word.title() for word in name.split('_'))


WS = {" ", "\n", "\t", "\r"}
CHARS = {";", "[", "]"}


class SpecTokenizer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def tokenize(self) -> t.Generator[str, None, None]:
        while self.pos < len(self.text):
            try:
                token = []
                while self.text[self.pos] not in (WS | CHARS):
                    token.append(self.text[self.pos])
                    self.pos += 1
                if token:
                    yield "".join(token)
                token = []
                while self.text[self.pos] in WS:
                    self.pos += 1
                if self.text[self.pos] in CHARS:
                    yield self.text[self.pos]
                    self.pos += 1
            except IndexError as e:
                break


@dataclass
class Node:
    __state__ = None
    children: t.List[t.Union["Node", str]] = field(default_factory=list)

    def add(self, node: "Node") -> None:
        self.children.append(node)


class NodeVisitor:
    def __init__(self, node: Node) -> None:
        self.node = node

    def visit(self) -> None:
        for child in self.node.children:
            try:
                if isinstance(child, Node):
                    getattr(self, "visit_" + child.__class__.__name__)(child)
                else:
                    getattr(self, "visit_" + type(child).__name__)(child)
            except AttributeError:
                pass

    def visit_leaf(self, leaf: str) -> None:
        pass


class StackFSM:
    __states__ = {}
    __root__ = None
    __tokenizer__ = None

    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = self.__tokenizer__(text).tokenize()
        self.stack = [self.__root__()]

    @property
    def tos(self) -> Node:
        return self.stack[-1]

    @property
    def state(self) -> str:
        return self.tos.__state__

    def append_child(self, child: t.Any) -> None:
        self.stack[-1].children.append(child)

    def pop_append(self) -> None:
        self.append_child(self.stack.pop())

    def push(self, node: Node) -> None:
        self.stack.append(node)

    def pop(self) -> None:
        self.stack.pop()

    def next(self) -> str:
        return next(self.tokens)

    def parse(self) -> Node:
        for token in self.tokens:
            # print(self.stack)
            # print("Next token:", token)
            # input(">>> ")
            getattr(self, f"handle_{self.state}")(token, self.tos)

        (node,) = self.stack

        return node


@dataclass
class Spec(Node):
    __state__ = "initial"


@dataclass
class Array(Node):
    type: t.Optional[str] = None
    size: t.Optional[int] = None


@dataclass
class NamedNode(Node):
    __state__ = "struct"

    name: t.Optional[str] = None


@dataclass
class Field(NamedNode):
    __state__ = "struct"

    type: t.Optional[str] = None


@dataclass
class Structure(NamedNode):
    __state__ = "struct"

    @property
    def fields(self) -> t.List[Field]:
        return self.children


@dataclass
class Union(Structure):
    __state__ = "union"


class SpecParser(StackFSM):
    __states__ = {"initial", "invalid", "struct", "union"}
    __tokenizer__ = SpecTokenizer
    __root__ = Spec

    def handle_initial(self, token: str, node: Spec) -> str:
        if token == "struct":
            name = self.next()

            if name == "{":
                # anonymous struct
                struct = Structure()
            else:
                struct = Structure(name=name)
                assert self.next() == "{"

            node.add(struct)
            self.push(struct)

        elif token == "union":
            union = Union(name=self.next())
            assert self.next() == "{"

            node.add(union)
            self.push(union)

    def handle_struct(self, token: str, node: Structure) -> str:
        if token == "}":
            # assert self.next() == ";"
            self.pop()
            return

        name = self.next()

        next = self.next()
        if next == ";":
            node.fields.append(Field(type=token, name=name))
            return

        if next == "[":
            # array
            size = int(self.next())
            assert self.next() == "]"
            assert self.next() == ";"
            node.fields.append(Field(type=Array(type=token, size=size), name=name))

    def handle_union(self, token: str, node: Union) -> str:
        if token == "}":
            assert self.next() == ";"
            self.pop()
            return

        if token == "struct":
            assert self.next() == "{"
            struct = Structure()
            node.fields.append(Field(type=struct))
            self.push(struct)
            return

        name = self.next()
        if name == ";":
            node.fields[-1].name = token
            return


class SpecVisitor(NodeVisitor):
    def __init__(self, node: Node) -> None:
        super().__init__(node)
        self._structures = set()

    def visit_Structure(self, node: Structure) -> None:
        self._structures.add(node.name)

        print(f"class {node.name}(Packet):")
        print("    _fields_ = [")

        for field in node.fields:
            name = camel_to_snake(field.name)
            if name.startswith(""):
                name = name[2:]
            if isinstance(field.type, Array):
                _type = (
                    field.type.type
                    if field.type.type in self._structures
                    else f"ctypes.c_{field.type.type}"
                )

                print(" " * 8 + f"('{name}', {_type} * {field.type.size}),")
            else:
                _type = (
                    field.type
                    if field.type in self._structures
                    else f"ctypes.c_{field.type}"
                )

                print(" " * 8 + f"('{name}', {_type}),")
        print("    ]")

    def visit_Union(self, node: Union) -> None:
        self._structures.add(node.name)

        for field in node.fields:
            field.type.name = snake_to_camel(camel_to_snake(field.name))
            self.visit_Structure(field.type)

        print(f"class {node.name}(ctypes.Union, PacketMixin):")
        print("    _fields_ = [")
        for field in node.fields:
            name = camel_to_snake(field.name)
            _type = snake_to_camel(camel_to_snake(field.name))
            print(" " * 8 + f"('{name}', {_type}),")
        print("    ]")


text = preprocess(Path("telemetry_f1_2021/data/spec.h").open().read())

spec = SpecParser(text).parse()
SpecVisitor(spec).visit()
