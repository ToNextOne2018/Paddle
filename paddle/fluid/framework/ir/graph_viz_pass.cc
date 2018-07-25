/* Copyright (c) 2018 PaddlePaddle Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. */

#include <algorithm>
#include <unordered_set>

#include "paddle/fluid/framework/ir/graph_viz_pass.h"

namespace paddle {
namespace framework {
namespace ir {

std::unique_ptr<ir::Graph> GraphVizPass::Apply(
    std::unique_ptr<ir::Graph> graph) const {
  std::unique_ptr<std::ostream> fout(new std::ofstream(graph_viz_path_));
  PADDLE_ENFORCE(fout->good());
  std::ostream& sout = *fout;

  size_t var_id = 0;
  std::unordered_map<const ir::Node*, size_t> vars;

  sout << "digraph G {\n";

  for (const ir::Node* n : graph->Nodes()) {
    if (n->NodeType() != ir::Node::Type::kVariable) continue;
    size_t cur_var_id = var_id++;
    vars[n] = cur_var_id;

    sout << "var_" << cur_var_id << " [label=\"" << n->Name() << "\"]"
         << std::endl;
  }

  size_t op_id = 0;
  for (const ir::Node* n : graph->Nodes()) {
    if (n->NodeType() != ir::Node::Type::kOperation) continue;
    std::string op_name = "op_" + std::to_string(op_id++);
    sout << op_name << " [label=\"" << n->Name() << "\", shape=rect]"
         << std::endl;
    for (auto in : n->inputs) {
      std::string var_name = "var_" + std::to_string(vars[in]);
      sout << var_name << " -> " << op_name << std::endl;
    }

    for (auto out : n->outputs) {
      std::string var_name = "var_" + std::to_string(vars[out]);
      sout << op_name << " -> " << var_name << std::endl;
    }
  }

  sout << "}\n";
  return graph;
}
}  // namespace ir
}  // namespace framework
}  // namespace paddle
