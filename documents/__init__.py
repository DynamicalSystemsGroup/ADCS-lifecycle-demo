"""Compiled engineering documents — deterministic views over the RDF dataset.

Every document in this package is a pure function of the persisted
quadstore: identical input quads (and identical input file bytes, for the
fingerprint) compile to byte-identical output. Built documents carry an
AUTO-GENERATED header and are never hand-edited — rebuild them from the
dataset instead, exactly like ontology/rtm.ttl is rebuilt from
rtm-edit.ttl.
"""
