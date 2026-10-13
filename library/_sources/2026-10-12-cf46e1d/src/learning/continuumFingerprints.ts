/** Continuum's approved recap fingerprints, kept outside Scalar's large fingerprint bank. */
export const CONTINUUM_LEARNING_FINGERPRINTS: Record<string, string> = {
  area: '9472b8ab7c6de2375af4fb4e36863f135f5e1a93d92959612895da7956d621c5',
  population: '1055006deaa9b5ccd1ba2a14af5eaf6d66c7641d4347a6eacfef81b9959711c1',
  gdp_per_capita: 'c7160d862cd8e4046b323938de5f089cbddb4833e7ae75f51bde11ec5840d2c4',
  AtomicNumber: '7885b7bf3590195c55470f5be16bda4a9be2ccb4c57316f621b3cdb9e96a9e6a',
  Density: '70998954055848ad2e4d46904be0454f5f8afae1b74042a1cd6fd6b515125859',
  AtomicRadius: 'f588c42e5a582c741047895490ec7b9feb033f91afbe45a912dbae8998d9cc71',
};

export function continuumLearningFingerprint(subjectId: string): string | null {
  return CONTINUUM_LEARNING_FINGERPRINTS[subjectId] ?? null;
}
