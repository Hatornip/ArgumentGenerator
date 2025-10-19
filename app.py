from flask import Flask, render_template, request, jsonify
from collections import defaultdict

app = Flask(__name__)

class ABAGenerator:
    def __init__(self):
        # Initialize the ABA framework components
        self.language = set()      # L: set of all sentences (language)
        self.assumptions = set()   # A: set of assumptions (special sentences)
        self.contraries = {}       # Maps each assumption to its contrary (contrary function)
        self.rules = {}            # Maps rule IDs to (head, body) pairs (R)
        self.preferences = []      # List of preference tuples (higher, lower) for ABA+

    def _parse_bracket_list(self, s):
        """
        Helper: Parses a string like "[a,b,c]" into a list ["a", "b", "c"].
        Used for parsing language, assumptions, and rule bodies.
        Handles malformed input by returning an empty list if parsing fails.
        """
        s = s.strip()
        if not s:
            return []
        # Extract content between brackets, if any
        if s.startswith('[') and ']' in s:
            inner = s[s.find('[') + 1:s.find(']')]
        else:
            inner = s
        # Split by comma, strip whitespace, and filter out empty strings
        parts = [p.strip() for p in inner.split(',') if p.strip()]
        return parts

    def parse_input(self, input_text):
        """
        Parses the input text into the ABA framework components.
        Expected format:
            L: [a,b,c]          # Language
            A: [a,b]            # Assumptions
            C(a): r             # Contrary of a is r
            [r1]: p <- q,a      # Rule r1: p if q and a
            PREF: a > b         # a is preferred over b
        Resets all attributes before parsing.
        """
        # Reset all attributes
        self.language = set()
        self.assumptions = set()
        self.contraries = {}
        self.rules = {}
        self.preferences = []
        lines = [line.strip() for line in input_text.split('\n') if line.strip()]
        for line in lines:
            # Parse language: L: [a,b,c]
            if line.startswith('L:'):
                rest = line[2:].strip()
                items = self._parse_bracket_list(rest)
                self.language = set(items)
            # Parse assumptions: A: [a,b]
            elif line.startswith('A:'):
                rest = line[2:].strip()
                items = self._parse_bracket_list(rest)
                self.assumptions = set(items)
            # Parse contraries: C(a): r
            elif line.startswith('C(') and ':' in line:
                left, right = line.split(':', 1)
                inside = left[left.find('(') + 1:left.find(')')].strip()
                contrary = right.strip()
                if inside:
                    self.contraries[inside] = contrary
            # Parse rules: [r1]: p <- q,a
            elif line.startswith('[') and ']:' in line:
                rule_id_part, rest = line.split(']:', 1)
                rule_id = rule_id_part[1:].strip()
                # Split head and body if there's a body
                if '<-' in rest:
                    head_part, body_part = rest.split('<-', 1)
                    head = head_part.strip()
                    body_items = self._parse_bracket_list(body_part.strip())
                else:
                    head = rest.strip()
                    body_items = []  # Fact (no body)
                self.rules[rule_id] = (head, body_items)
            # Parse preferences: PREF: a > b
            elif line.startswith('PREF:'):
                rest = line[len('PREF:'):].strip()
                if rest:
                    parts = [p.strip() for p in rest.split('>') if p.strip()]
                    for i in range(len(parts) - 1):
                        self.preferences.append((parts[i], parts[i + 1]))

    def is_framework_circular(self):
        """
        Checks if the framework is circular using DFS.
        A framework is circular if there is a cycle in the dependency graph of non-assumptions.
        This is a standard cycle detection algorithm.
        """
        non_assumps = set(self.language) - set(self.assumptions)
        graph = defaultdict(list)
        nodes = set()
        # Build the dependency graph for non-assumptions
        for rule_id, (head, body) in self.rules.items():
            if head in non_assumps:
                nodes.add(head)
            for b in body:
                if b in non_assumps:
                    nodes.add(b)
                    if head in non_assumps:
                        graph[head].append(b)
        # DFS color coding: WHITE=unvisited, GRAY=visiting, BLACK=visited
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in nodes}
        def dfs(u):
            color[u] = GRAY
            for v in graph.get(u, []):
                if color[v] == GRAY:
                    return True  # Cycle detected
                if color[v] == WHITE and dfs(v):
                    return True
            color[u] = BLACK
            return False
        # Run DFS from each unvisited node
        for n in nodes:
            if color[n] == WHITE:
                if dfs(n):
                    return True
        return False

    def is_framework_atomic(self):
        """
        Checks if all rules are atomic (i.e., their bodies contain only assumptions).
        This is a requirement for atomic ABA frameworks.
        """
        for head, body in self.rules.values():
            if not all(p in self.assumptions for p in body):
                return False
        return True

    def get_arguments(self):
        """
        Computes all arguments in the framework.
        An argument is a tree with leaves in assumptions and root in language.
        This is a fixed-point algorithm: keep adding arguments until no more can be added.
        """
        arguments = []
        # Start with arguments for each assumption
        for ass in sorted(self.assumptions):
            arguments.append({
                'id': f'a{len(arguments) + 1}',
                'claim': ass,
                'assumptions': {ass},
                'rules': set()
            })
        # Map claim to argument for quick lookup
        arg_dict = {arg['claim']: arg for arg in arguments}
        changed = True
        while changed:
            changed = False
            # For each rule, check if all body items are already arguments
            for rule_id, (head, body) in sorted(self.rules.items()):
                body_args = []
                for b in body:
                    if b in arg_dict:
                        body_args.append(arg_dict[b])
                    else:
                        break  # Not all body items are arguments yet
                else:
                    # All body items are arguments; build new argument
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
        # Sort for consistent output
        for arg in arguments:
            arg['assumptions'] = sorted(list(arg['assumptions']))
            arg['rules'] = sorted(list(arg['rules']))
        return arguments

    def make_non_circular(self):
        """
        Transforms a circular ABA framework into a non-circular one.
        This is done by "unfolding" the framework: for each non-assumption s,
        create k copies s^1, s^2, ..., s^k, where k is the number of non-assumptions.
        This breaks cycles by introducing intermediate steps.
        """
        non_assumptions = sorted(list(self.language - self.assumptions))
        k = len(non_assumptions)
        if k == 0:
            return  # No non-assumptions, nothing to do
        new_language = set(self.language)
        # Add indexed copies of each non-assumption
        for s in non_assumptions:
            for i in range(1, k):
                new_language.add(f"{s}^{i}")
        new_rules = {}
        # For each rule, create k copies with indexed heads and bodies
        for rule_id, (head, body) in sorted(self.rules.items()):
            is_atomic = all(p in self.assumptions for p in body)
            if is_atomic:
                # For atomic rules, create k copies with indexed heads
                for i in range(1, k + 1):
                    new_head = f"{head}^{i}" if i < k else head
                    new_rules[f"{rule_id}_{i}"] = (new_head, list(body))
            else:
                # For non-atomic rules, create k-1 copies with indexed heads and bodies
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
        """
        Transforms a non-circular ABA framework into an atomic one.
        For each non-assumption s, introduce two new assumptions: s_d and s_nd.
        Replace each occurrence of s in rule bodies with s_d.
        Set contraries: s_d's contrary is s_nd, and s_nd's contrary is s.
        """
        new_assumptions = set(self.assumptions)
        new_language = set(self.language)
        new_contraries = dict(self.contraries)
        new_rules = {}
        # For each non-assumption, add s_d and s_nd to assumptions and language
        for s in sorted(self.language - self.assumptions):
            s_d = f"{s}_d"
            s_nd = f"{s}_nd"
            new_assumptions.add(s_d)
            new_assumptions.add(s_nd)
            new_language.add(s_d)
            new_language.add(s_nd)
            new_contraries[s_d] = s_nd
            new_contraries[s_nd] = s
        # For each rule, replace non-assumptions in body with s_d
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
        """
        Builds a preference relation dictionary from the list of preferences.
        This is used for ABA+ attack resolution.
        """
        pref_rel = defaultdict(set)
        for higher, lower in self.preferences:
            pref_rel[higher].add(lower)
        return pref_rel

    def get_attacks(self):
        """
        Computes all attacks between arguments, considering preferences (ABA+).
        There are two types of attacks:
            - Normal attack: a attacks b if a's claim is the contrary of an assumption in b,
              and no assumption in a is less preferred than the attacked assumption in b.
            - Reverse attack: b attacks a if b's claim is the contrary of an assumption in a,
              and b has a more preferred assumption than the attacked assumption in a.
        """
        attacks = []
        args = self.get_arguments()
        pref_rel = self.build_preference_relation()
        id_map = {arg['id']: arg for arg in args}
        claim_map = {arg['claim']: arg for arg in args}
        for a in args:
            for b in args:
                # Check for normal attacks: a attacks b
                for ass_b in b['assumptions']:
                    if ass_b in self.contraries and self.contraries[ass_b] == a['claim']:
                        normal_attack_valid = True
                        # Check if any assumption in a is less preferred than ass_b
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
                # Check for reverse attacks: b attacks a
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
    """Renders the main page with the input form."""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """
    Endpoint for processing input and returning the original, non-circular, and atomic frameworks.
    Steps:
        1. Parse input into original framework.
        2. If circular, transform to non-circular.
        3. If not atomic, transform to atomic.
        4. Return all frameworks as JSON.
    """
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
    # Non-circular transformation
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
    # Atomic transformation
    atomic = ABAGenerator()
    if 'non_circular' in result:
        # Use non-circular as base if available
        atomic.language = set(result['non_circular']['language'])
        atomic.assumptions = set(result['non_circular']['assumptions'])
        atomic.contraries = dict(result['non_circular']['contraries'])
        atomic.rules = dict(result['non_circular']['rules'])
        atomic.preferences = list(result['non_circular']['preferences'])
    else:
        # Otherwise, use original
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
