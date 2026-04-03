import { useQuery } from "@tanstack/react-query";
import { listDepartments } from "@/api/departments";

export function useDepartments() {
  return useQuery({
    queryKey: ["departments"],
    queryFn: () => listDepartments({ size: 100 }),
  });
}
