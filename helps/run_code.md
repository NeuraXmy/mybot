# 代码运行服务 (run_code)

> 基于 glot.io 提供代码运行服务


###  用户指令

- [`/code` 运行代码](#code)

### 管理指令

无

---


## `/code`

> 指定语言和标准输入运行代码，返回标准输出。支持语言：
py/php/java/cpp/js/c#/c/go/asm/ats/bash/clisp/clojure/cobol/coffeescript/crystal/d/elixir/elm/erlang/fsharp/groovy/guide/hare/haskell/idris/julia/kotlin/lua/mercury/nim/nix/ocaml/pascal/perl/raku/ruby/rust/sac/scala/swift/typescript/zig/plaintext

- **指令别名**

    `/run`

- **示例**

```
/code py 1 2
a, b = map(int, input().split())
print(a + b)
```
其中，`py` 为指定语言，`1 2` 为指定输入


--- 

[回到帮助目录](./main.md)