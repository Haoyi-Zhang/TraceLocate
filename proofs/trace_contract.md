# Finite trace contract and complete mathematical arguments

These are mathematical proofs written in ordinary notation. Executable tests check finite instances; no proof assistant has mechanically established the universally quantified theorems. The furthest-reaching edit frontier is classical (Myers, Algorithmica, 1986); the retained proposed deduction is the labelled local blocking proof and its tap-core bound. Priority of that deduction is not certified by this document.

## 1. Inputs, projection, and universal localization

Let M be a finite set of m coordinates. A row is a tuple in the product of finite coordinate alphabets. All words in this document have the same length h >= 1. Select S subset M; pi_S projects each complete row and does not split its time index. Del_d(x) is the set of all projected words obtained by deleting at most d whole rows from pi_S(x), where 0 <= d <= h. Loss locations are not recorded. For each reliably known context c and class f, L[c,f] is a nonempty finite language of h-row words. The promised contract is

  for every c, every f != g, every x in L[c,f], every y in L[c,g]:
      Del_d(pi_S(x)) intersection Del_d(pi_S(y)) is empty.

Fault classes need not be singleton machines or singleton words. Initial states and capture offsets are included in language enumeration. Different contexts are not compared. An unknown context would require a union and is a different instance. The theorem concerns exactly the given languages, not correctness of a physical extraction process.

### Proposition 1 (standard subsequence characterization)
The contract holds exactly when LCS(pi_S(x),pi_S(y)) < h-d for every required pair.

Proof. Any common observed word has length at least h-d and is a common subsequence. Conversely, a common subsequence of length at least h-d contains one of length exactly h-d, obtained from each word by precisely d deletions. Hence it is an admitted common observation. Taking the negation and then the universal pair quantifier proves the statement. If d=h, the empty word is common to every pair, so the contract is impossible for two nonempty classes. End.

### Lemma 1A (projection monotonicity)
If S is a subset of T, then LCS(pi_T(x),pi_T(y)) <= LCS(pi_S(x),pi_S(y)). Hence coverage is upward-closed in the selected taps. If the full interface M is ambiguous, every subset is ambiguous.

Proof. Equality of two rows after projection to T implies equality after the coarser projection to S. Every common subsequence under T is therefore also a common subsequence under S, proving the inequality. Proposition 1 gives the coverage consequences. End.

This observation justifies testing the full interface before mask search. It also shows that a union of separately sufficient per-pair tap sets remains sufficient for all of those pairs. It does not bound the size of that union independently of the number of required pairs.

## 2. Augmented edit graph

Number consumed prefixes from zero. A state is (i,j,a,b): i rows of x and j rows of y have been consumed; a deletions were made from x and b from y. A matching step increases i and j together, and is allowed precisely when i<h, j<h, and pi_S(x[i])=pi_S(y[j]). An x-deletion increases i and a; a y-deletion increases j and b. Deletion edges remain allowed outside the finite words, while there are no out-of-range matching edges. Equivalently, extend x and y with disjoint virtual alphabets. Every path satisfies j=i-a+b.

### Lemma 2 (exact-budget completion)
A common subsequence of length at least h-d exists exactly when a path with a=b=d reaches i=j>=h in the augmented graph.

Proof. If a common subsequence has length k>=h-d, its alignment consumes both words using h-k deletions per side. Append d-(h-k) virtual deletions on each side. The final equal indices are h+d-(h-k)>=h and the deletion counts are d,d. Conversely, consider a path to equal indices >=h with d deletions on each side. Matching edges occur only within both words. Let k be their number. Restricting the path to its real-row matching edges produces an increasing alignment. Consuming the h real rows of each word required h-k real deletions, no more than d. Therefore k>=h-d. End.

Virtual deletion is proof machinery, not an acquisition event. It avoids an invalid assumption that a failure at a smaller deletion count cannot matter at the terminal exact count.

## 3. Local upper-bound certificate

For each 0<=a,b<=d provide an integer U[a,b]. Put V[a,b]=U[a,b]-a+b. In a cell whose two indices are in range, provide a coordinate p[a,b] in S. Otherwise provide a distinguished null boundary marker. Require:

(A) a <= U[a,b] <= h+a.
(B) If a>0, U[a,b] >= U[a-1,b]+1.
(C) If b>0, U[a,b] >= U[a,b-1].
(D) If U[a,b]<h and V[a,b]<h, x[U[a,b]][p] != y[V[a,b]][p]. Otherwise the cell uses the fixed null boundary marker.
(E) U[d,d] < h.

The arithmetic bound implies V[a,b]>=b>=0, so (D) never uses a negative row index. A finite boundary is checked using one selected coordinate only, not an equality scan over an intervening prefix.

### Theorem 3 (soundness)
Every accepted local certificate proves separation of the supplied pair under d silent deletions per record.

Proof. We show by induction on a+b that every reachable state with deletion counts (a,b) has x-index at most U[a,b]. With no deletions, the only possible movement is along matching edges from (0,0). Bound (A) makes U[0,0] nonnegative. The outgoing matching edge at that bound is absent by (D), either because its rows disagree at the selected coordinate or because it is out of range. Thus no matching-only path can pass the bound.

For a+b>0, take any path at these counts and locate its last deletion. If it is from x, the preceding x-index is at most U[a-1,b] by the induction hypothesis. Immediately after that deletion its index is at most U[a-1,b]+1<=U[a,b]. If it is from y, the x-index remains at most U[a,b-1]<=U[a,b]. All following steps are matching steps on the fixed diagonal j=i-a+b. Such a run starts at or before U[a,b] and cannot cross the absent matching edge there. This proves the induction for all paths, including those whose earlier deletion positions differ from the producer's choices. By (E), no (d,d) path reaches index h. Lemma 2 gives separation. End.

A consumer need not establish that each upper bound is reachable, minimal, or equal to the producer's frontier. Slack upper bounds are valid when all local conditions hold. Mutating a certificate does not necessarily invalidate it; mutation tests deliberately target violated obligations rather than arbitrary byte changes.

### Lemma 4 (furthest-reaching recurrence)
Let F[a,b] be the largest x-index of a reachable augmented-graph state at deletion counts (a,b). It is finite and at most h+a. Define seed(0,0)=0 and otherwise

  seed(a,b)=max({F[a-1,b]+1 if a>0} union {F[a,b-1] if b>0}).

Starting at i=seed(a,b), j=i-a+b, repeatedly take matching edges until the first mismatch or out-of-range position. The resulting i equals F[a,b].

Proof. Every path contains at most h matching edges and exactly a x-deletions, so its x-index is at most h+a. The reachable index set is nonempty and finite; a maximum exists. For the zero state a matching-only run gives precisely the maximum. At other states, the maximum seed is attainable by a last deletion from an attainable maximum predecessor, so its matching extension is attainable. Consider any other path and the position immediately after its last deletion, at x-index r<=seed. Its remaining matching run ends either before seed, or reaches seed using the same fixed diagonal. In the latter case the suffix from seed uses exactly the same equality predicate as the greedy extension from seed. Its endpoint cannot exceed that extension. Thus no other path reaches further. End.

This is the standard dominance argument for an edit frontier, here indexed by separate deletion budgets. It is not presented as a new longest-common-subsequence algorithm.

### Theorem 5 (completeness and tap core)
A pair is separated under S and budget d if and only if it has a certificate satisfying (A)-(E). If separated, some subset T of S of size at most min(|S|,(d+1)^2) also separates it.

Proof. Soundness is Theorem 3. For completeness use U=F from Lemma 4. It satisfies the range and predecessor conditions. Each greedy run stops at a mismatch or boundary; at a mismatch choose any differing coordinate in S, which exists by the definition of projection. Since the pair is separated, Lemma 2 implies F[d,d]<h. This is a certificate. Let T contain the coordinates occurring as its finite mismatch pointers. At most one coordinate is recorded in each of (d+1)^2 cells. Under T every recorded finite mismatch remains a mismatch. Arithmetic and boundary conditions are unchanged. The same certificate is accepted, and soundness gives separation under T. End.

A fixed-width encoding uses O((d+1)^2 (log(h+d+1)+log(m+1))) bits for this local proof, excluding the words and identity of the pair. Local checking uses O((d+1)^2) indexed coordinate comparisons and integer operations. Bit-operation complexity includes the cost of integer arithmetic and indexed access. In the packed binary implementation tap counts are bounded; no claim treats arbitrary-precision word operations as constant at unbounded m.

## 4. An essential linear-size family

### Proposition 6
For every d>=0 there is a separated pair that requires all 2d+1 coordinates. Consequently no universal upper bound independent of d is possible.

Proof. Set h=d+1 and m=2d+1. For k=0,...,2h-1 let v_k be the m-bit row whose first k bits are one and the remainder zero. Set x=(v_0,v_2,...,v_{2h-2}) and y=(v_1,v_3,...,v_{2h-1}). All 2h rows are distinct, so the full projection has no common one-row subsequence. Every retained record has length at least one, and the pair is separated. For any p=0,...,m-1, rows v_p and v_{p+1} differ only at coordinate p. Their indices have opposite parity, so they belong to opposite words. Removing coordinate p makes these rows equal and creates a legal common record of length one. Every coordinate is therefore essential. End.

The upper and lower bounds do not match. No proof here establishes that either (d+1)^2 or 2d+1 is the tight general bound. The existence of a small core for each pair also does not bound one global interface independently of the number of pairs: different pairs may force disjoint coordinates.

For d=1 the instance is x=(000,011), y=(001,111), using binary strings displayed most-significant bit first. All three taps are necessary jointly. Any single-tap-marginal selection rule misses this feasible interface. The indicator of pair separation is not generally submodular: adding the last essential tap to the other two changes the indicator from zero to one, whereas adding it to the empty set leaves zero. Thus a greedy approximation justified by ordinary submodular coverage does not follow for this objective.

## 5. Exact bounded interface synthesis

Let an alignment A=((i_1,j_1),...,(i_k,j_k)) have k=h-d, with both index sequences strictly increasing. Let D(A) be the set of all full-tap coordinates that differ at some aligned row pair. The clause associated with A is S intersection D(A) != empty.

### Lemma 7
Every robust interface satisfies every such alignment clause, irrespective of which candidate produced the alignment.

Proof. If S misses D(A), all k aligned projected rows are equal, so A is a common observation admitted at budget d. This contradicts robustness. End.

Start with no clauses. Choose a minimum-positive-cost mask satisfying the accumulated clauses, with any fixed tie rule. Check every required pair. If one collides, retain an alignment of length h-d and its clause. If D(A) is empty, even the full interface is infeasible. Otherwise iterate.

### Theorem 8 (finite termination and minimum cost)
With m finite taps, refinement terminates after at most 2^m distinct candidates. A verified candidate is a globally minimum-cost robust interface. An empty clause proves full-interface infeasibility.

Proof. The failing candidate misses the clause just obtained, so it cannot recur. There are only 2^m candidates. Every genuinely robust mask satisfies every learned clause by Lemma 7, so no robust mask is excluded. Therefore the process either proves an empty necessary clause or eventually verifies a candidate. At verification, the selected mask minimizes cost over a relaxation containing all robust masks; since it is itself robust, its cost equals the true minimum. An empty clause is unsatisfiable for every mask. End.

The implementation first certifies the minimum loss of the full interface and returns an impossibility witness if that margin does not exceed d. On feasible instances it performs the refinement above. Positive costs permit minimum-cardinality campaigns as the special case of unit costs. The independent consumer verifies each clause from a concrete alignment and enumerates all cheaper masks. It accepts optimality exactly when every cheaper mask fails at least one necessary clause. This lower-bound check is bounded exponential work (m<=12 in the implemented optimum checker), not a general polynomial proof system or a SAT-proof implementation.

## 6. Smallest ambiguity witness at a fixed horizon

For a fixed mask S define

  ell(S)=h-max over required pairs LCS(pi_S(x),pi_S(y)).

### Theorem 9
ell(S) is the smallest per-record loss budget admitting any cross-class common observation. An alignment of length h-ell(S), together with complete pair separation certificates at budget ell(S)-1 when ell(S)>0, proves this minimum without a longest-common-subsequence calculation in the consumer.

Proof. Proposition 1 identifies a collision at budget e with the existence of a pair whose LCS is at least h-e. Rearranging and minimizing e gives the formula. The supplied alignment establishes a collision at ell. Complete coverage below ell rules out every smaller budget, since deleting fewer rows only shrinks the set of possible observations. For ell=0 the identical full observation already meets the nonnegative lower bound on deletions, so there is no below-zero proof obligation. End.

The delivered full-margin certificate uses S equal to all taps. It proves that no tap selection can repair infeasibility when ell(M)<=d: projection cannot destroy a full-row equality. For a feasible returned mask the primary certificate proves requested coverage and minimum cost; its own exact margin need not be the same as ell(M). The source function supports computing that separate margin, but the campaign reports ell(M) only. Do not label it the selected-interface margin.

The local coverage component has P(d+1)^2 entries for P required pairs. The optional full-margin below-proof uses P*ell(M)^2 entries and can be larger when ell(M)>d+1. Alignment clauses take O(rh) index pairs for r refinements. Pair enumeration, model replay, raw words, and bounded cheaper-mask enumeration remain additional costs.

## 7. Exact enumeration and trust

The independent consumer validates the total transition tables and stimulus lengths, iterates all declared class variants, all initial states and all offsets, and deduplicates full words canonically. It then enumerates the full Cartesian product for every distinct class pair in each known context. A coverage packet must contain precisely these ordered pair identifiers; omission, duplication or order mismatch is rejected. The producer and consumer are separate implementations, but use the same supplied specification and ordinary Python runtime. This is implementation separation, not an independent author review, a proof-assistant result, or a verified translation from RTL. If the supplied finite model omits a physical behavior, certificate checking cannot reconstruct it.

## 8. All-input indistinguishability in the shift-register example

The wrong-feedback and rotate variants both admit initial state 3. In states C={3,5,6}, their feedback bits agree and their full seven-tap rows agree for both possible input symbols. Input zero holds the state. Input one cycles 3->6->5->3. Thus C is closed for all inputs and both variants produce exactly the same full-tap word for every input sequence and every horizon from that common initial state. A three-state, six-transition equality-and-closure witness proves this directly from the supplied tables. No horizon increase, tap addition, or improved loss tolerance can universally separate these two declared classes. This is a standard finite invariant argument, not a new bisimulation method.
