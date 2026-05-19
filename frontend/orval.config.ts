import { defineConfig } from "orval"

export default defineConfig({
  oskar: {
    input: {
      target: "http://localhost:8000/openapi.json",
    },
    output: {
      mode: "tags-split",
      target: "src/api/generated",
      schemas: "src/api/generated/model",
      client: "react-query",
      httpClient: "axios",
      override: {
        mutator: {
          path: "src/api/axios.ts",
          name: "axiosInstance",
        },
        query: {
          useQuery: true,
          useMutation: true,
        },
      },
    },
  },
})
