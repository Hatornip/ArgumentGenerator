from flask import Flask, render_template, request, jsonify
from collections import defaultdict

app = Flask(__name__)


class ABAGenerator:
    def __init__(self):
        self.language = set()
        self.assumptions = set()
        self.contraries = {}
        self.rules = {}
        self.preferences = []

    def _parse_bracket_list(self, s):
        s = s.strip()
        if not s:
            return []
        if s.startswith('[') and ']' in s:
            inner = s[s.find('[') + 1:s.find(']')]
        else:
            inner = s
        parts = [p.strip() for p in inner.split(',') if p.strip()]
        return parts

    def parse_input(self, input_text):
        self.language = set()
        self.assumptions = set()
        self.contraries = {}
        self.rules = {}
        self.preferences = []

        lines = [line.strip() for line in input_text.split('\n') if line.strip()]
        for line in lines:
            if line.startswith('L:'):
                rest = line[2:].strip()
                items = self._parse_bracket_list(rest)
                self.language = set(items)
            elif line.startswith('A:'):
                rest = line[2:].strip()
                items = self._parse_bracket_list(rest)
                self.assumptions = set(items)
            elif line.startswith('C(') and ':' in line:
                left, right = line.split(':', 1)
                inside = left[left.find('(') + 1:left.find(')')].strip()
                contrary = right.strip()
                if inside:
                    self.contraries[inside] = contrary
            elif line.startswith('[') and ']:' in line:
                rule_id_part, rest = line.split(']:', 1)
                rule_id = rule_id_part[1:].strip()
                if '<-' in rest:
                    head_part, body_part = rest.split('<-', 1)
                    head = head_part.strip()
                    body_items = self._parse_bracket_list(body_part.strip())
                else:
                    head = rest.strip()
                    body_items = []
                self.rules[rule_id] = (head, body_items)
            elif line.startswith('PREF:'):
                rest = line[len('PREF:'):].strip()
                if rest:
                    parts = [p.strip() for p in rest.split('>') if p.strip()]
                    for i in range(len(parts) - 1):
                        self.preferences.append((parts[i], parts[i + 1]))

    def is_framework_circular(self):
        non_assumps = set(self.language) - set(self.assumptions)
        graph = defaultdict(list)
        nodes = set()
        for rule_id, (head, body) in self.rules.items():
            if head in non_assumps:
                nodes.add(head)
            for b in body:
                if b in non_assumps:
                    nodes.add(b)
                    if head in non_assumps:
                        graph[head].append(b)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in nodes}

        def dfs(u):
            color[u] = GRAY
            for v in graph.get(u, []):
                if color[v] == GRAY:
                    return True
                if color[v] == WHITE and dfs(v):
                    return True
            color[u] = BLACK
            return False

        for n in nodes:
            if color[n] == WHITE:
                if dfs(n):
                    return True
        return False

    def is_framework_atomic(self):
        for head, body in self.rules.values():
            if not all(p in self.assumptions for p in body):
                return False
        return True

    def get_arguments(self):
        arguments = []
        for ass in sorted(self.assumptions):
            arguments.append({
                'id': f'a{len(arguments) + 1}',
                'claim': ass,
                'assumptions': {ass},
                'rules': set()
            })
        arg_dict = {arg['claim']: arg for arg in arguments}

        changed = True
        while changed:
            changed = False
            for rule_id, (head, body) in sorted(self.rules.items()):
                body_args = []
                for b in body:
                    if b in arg_dict:
                        body_args.append(arg_dict[b])
                    else:
                        break
                else:
                    assumptions = set()
                    rules = set()
                    for ba in body_args:
                        assumptions.update(ba['assumptions'])
                        rules.update(ba['rules'])
                    rules.add(rule_id)
                    new_arg = {
                        'id': f'a{len(arguments) + 1}',
                        'claim': head,
                        'assumptions': assumptions,
                        'rules': rules
                    }
                    if head not in arg_dict:
                        arg_dict[head] = new_arg
                        arguments.append(new_arg)
                        changed = True

        for arg in arguments:
            arg['assumptions'] = sorted(list(arg['assumptions']))
            arg['rules'] = sorted(list(arg['rules']))
        return arguments

    def make_non_circular(self):
        non_assumptions = sorted(list(self.language - self.assumptions))
        k = len(non_assumptions)
        if k == 0:
            return

        new_language = set(self.language)
        for s in non_assumptions:
            for i in range(1, k):
                new_language.add(f"{s}^{i}")

        new_rules = {}

        for rule_id, (head, body) in sorted(self.rules.items()):
            is_atomic = all(p in self.assumptions for p in body)
            if is_atomic:
                for i in range(1, k + 1):
                    new_head = f"{head}^{i}" if i < k else head
                    new_rules[f"{rule_id}_{i}"] = (new_head, list(body))
            else:
                for i in range(2, k + 1):
                    new_head = f"{head}^{i}" if i < k else head
                    new_body = []
                    for p in body:
                        if p in self.assumptions:
                            new_body.append(p)
                        else:
                            new_body.append(f"{p}^{i-1}" if (i - 1) < k else p)
                    new_rules[f"{rule_id}_{i}"] = (new_head, new_body)

        self.language = new_language
        self.rules = new_rules

    def make_atomic(self):
        new_assumptions = set(self.assumptions)
        new_language = set(self.language)
        new_contraries = dict(self.contraries)
        new_rules = {}

        for s in sorted(self.language - self.assumptions):
            s_d = f"{s}_d"
            s_nd = f"{s}_nd"
            new_assumptions.add(s_d)
            new_assumptions.add(s_nd)
            new_language.add(s_d)
            new_language.add(s_nd)
            new_contraries[s_d] = s_nd
            new_contraries[s_nd] = s

        for rule_id, (head, body) in sorted(self.rules.items()):
            new_body = []
            for p in body:
                if p in self.assumptions:
                    new_body.append(p)
                else:
                    new_body.append(f"{p}_d")
            new_rules[rule_id] = (head, new_body)

        self.assumptions = new_assumptions
        self.language = new_language
        self.contraries = new_contraries
        self.rules = new_rules

    def build_preference_relation(self):
        pref_rel = defaultdict(set)
        for higher, lower in self.preferences:
            pref_rel[higher].add(lower)
        return pref_rel

    def get_attacks(self):
        attacks = []
        args = self.get_arguments()
        pref_rel = self.build_preference_relation()

        id_map = {arg['id']: arg for arg in args}
        claim_map = {arg['claim']: arg for arg in args}

        for a in args:
            for b in args:
                for ass_b in b['assumptions']:
                    if ass_b in self.contraries and self.contraries[ass_b] == a['claim']:
                        normal_attack_valid = True
                        for ass_a in a['assumptions']:
                            if (ass_a, ass_b) in self.preferences:
                                normal_attack_valid = False
                                break
                        if normal_attack_valid:
                            attacks.append({
                                'attacker': a['id'],
                                'attacked': b['id'],
                                'type': 'normal'
                            })
                for ass_a in a['assumptions']:
                    if ass_a in self.contraries and self.contraries[ass_a] == b['claim']:
                        reverse_attack_valid = any(
                            (ass_b, ass_a) in self.preferences for ass_b in b['assumptions']
                        )
                        if reverse_attack_valid:
                            attacks.append({
                                'attacker': b['id'],
                                'attacked': a['id'],
                                'type': 'reverse'
                            })
        return attacks


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process():
    input_text = request.json['input']

    original = ABAGenerator()
    original.parse_input(input_text)
    original_arguments = original.get_arguments()
    original_attacks = original.get_attacks()
    result = {
        'original': {
            'language': sorted(list(original.language)),
            'assumptions': sorted(list(original.assumptions)),
            'contraries': original.contraries,
            'rules': original.rules,
            'preferences': original.preferences,
            'arguments': original_arguments,
            'attacks': original_attacks,
        }
    }

    non_circular = ABAGenerator()
    non_circular.parse_input(input_text)
    if non_circular.is_framework_circular():
        non_circular.make_non_circular()
        non_circular_arguments = non_circular.get_arguments()
        non_circular_attacks = non_circular.get_attacks()
        result['non_circular'] = {
            'language': sorted(list(non_circular.language)),
            'assumptions': sorted(list(non_circular.assumptions)),
            'contraries': non_circular.contraries,
            'rules': non_circular.rules,
            'preferences': non_circular.preferences,
            'arguments': non_circular_arguments,
            'attacks': non_circular_attacks,
        }

    atomic = ABAGenerator()
    if 'non_circular' in result:
        atomic.language = set(result['non_circular']['language'])
        atomic.assumptions = set(result['non_circular']['assumptions'])
        atomic.contraries = dict(result['non_circular']['contraries'])
        atomic.rules = dict(result['non_circular']['rules'])
        atomic.preferences = list(result['non_circular']['preferences'])
    else:
        atomic.language = set(result['original']['language'])
        atomic.assumptions = set(result['original']['assumptions'])
        atomic.contraries = dict(result['original']['contraries'])
        atomic.rules = dict(result['original']['rules'])
        atomic.preferences = list(result['original']['preferences'])

    if not atomic.is_framework_atomic():
        atomic.make_atomic()
        atomic_arguments = atomic.get_arguments()
        atomic_attacks = atomic.get_attacks()
        result['atomic'] = {
            'language': sorted(list(atomic.language)),
            'assumptions': sorted(list(atomic.assumptions)),
            'contraries': atomic.contraries,
            'rules': atomic.rules,
            'preferences': atomic.preferences,
            'arguments': atomic_arguments,
            'attacks': atomic_attacks,
        }

    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True)
