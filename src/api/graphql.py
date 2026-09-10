"""GraphQL schema and resolvers. Types follow contracts/graphql/schema.graphql (ADR-002)."""

TYPE_DEFS = """
type CertificationDossier {
  id: ID!
  target: String!
  status: String!
  scores: [Score!]!
  validUntil: String!
}

type Score {
  dimension: String!
  value: Float!
}

type RemediationItem {
  risk: String!
  action: String!
  owner: String!
}

type Query {
  dossiers: [CertificationDossier!]!
  dossier(id: ID!): CertificationDossier
}

type Mutation {
  buildDossier(target: String!): CertificationDossier!
  publishDossier(id: ID!): CertificationDossier!
}

"""

resolvers = {
    "Query": {},
    "Mutation": {},
}
