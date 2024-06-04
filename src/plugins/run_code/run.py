# python3
# -*- coding: utf-8 -*-
# @Time    : 2021/11/22 14:17
# @Author  : yzyyz
# @Email   :  youzyyz1384@qq.com
# @File    : run.py
# @Software: PyCharm

# @Time    : 2023/01/19 21:00
# @UpdateBy: Limnium
# 更新了正则的pattern，完善了返回机制，“优化”代码风格。
import re
import httpx

codeType = {
    'py': ['python', 'py'],
    'cpp': ['cpp', 'cpp'],
    'java': ['java', 'java'],
    'php': ['php', 'php'],
    'js': ['javascript', 'js'],
    'c': ['c', 'c'],
    'c#': ['csharp', 'cs'],
    'go': ['go', 'go'],
    'asm': ['assembly', 'asm'],
    'ats': ['ats','dats'],
    'bash': ['bash','sh'],
    'clisp': ['clisp','lsp'],
    'clojure': ['clojure','clj'],
    'cobol': ['cobol','cob'],
    'coffeescript': ['coffeescript','coffee'],
    'crystal': ['crystal','cr'],
    'D': ['D','d'],
    'elixir': ['elixir','ex'],
    'elm': ['elm','elm'],
    'erlang': ['erlang','erl'],
    'fsharp': ['fsharp','fs'],
    'groovy': ['groovy','groovy'],
    'guile': ['guile','scm'],
    'hare': ['hare','ha'],
    'haskell': ['haskell','hs'],
    'idris': ['idris','idr'],
    'julia': ['julia','jl'],
    'kotlin': ['kotlin','kt'],
    'lua': ['lua','lua'],
    'mercury': ['mercury','m'],
    'nim': ['nim','nim'],
    'nix': ['nix','nix'],
    'ocaml': ['ocaml','ml'],
    'pascal': ['pascal','pp'],
    'perl': ['perl','pl'],
    'raku': ['raku','raku'],
    'ruby': ['ruby','rb'],
    'rust': ['rust','rs'],
    'sac': ['sac','sac'],
    'scala': ['scala','scala'],
    'swift': ['swift','swift'],
    'typescript': ['typescript','ts'],
    'zig': ['zig','zig'],
    'plaintext': ['plaintext','txt']
}


async def run(strcode):
    strcode = strcode.replace('&amp;', '&').replace('&#91;', '[').replace('&#93;', ']')
    try:
        a = re.match(r'(py|php|java|cpp|js|c#|c|go|asm|ats|bash|clisp|clojure|cobol|coffeescript|crystal|d|elixir|elm|erlang|fsharp|groovy|guide|hare|haskell|idris|julia|kotlin|lua|mercury|nim|nix|ocaml|pascal|perl|raku|ruby|rust|sac|scala|swift|typescript|zig|plaintext)\b ?(.*)\n((?:.|\n)+)', strcode)
        lang, stdin, code = a.group(1), a.group(2).replace(' ', '\n'), a.group(3)
    except:
        return "输入有误，目前仅支持py/php/java/cpp/js/c#/c/go/asm/ats/bash/clisp/clojure/cobol/coffeescript/crystal/d/elixir/elm/erlang/fsharp/groovy/guide/hare/haskell/idris/julia/kotlin/lua/mercury/nim/nix/ocaml/pascal/perl/raku/ruby/rust/sac/scala/swift/typescript/zig/plaintext"
    dataJson = {
        "files": [
            {
                "name": f"main.{codeType[lang][1]}",
                "content": code
            }
        ],
        "stdin": stdin,
        "command": ""
    }
    headers = {"Authorization": "Token 0123456-789a-bcde-f012-3456789abcde",
               "content-type": "application/"}
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url=f'https://glot.io/run/{codeType[lang][0]}?version=latest', headers=headers, json=dataJson)
    except httpx.ReadTimeout:
        raise Exception("请求超时")
    except Exception as e:
        raise Exception(f"请求失败: {type(e).__name__} {e}")
    
    if res.status_code == 200:
        res = res.json()
        # print(res)
        return res['stdout']+('\n---\n'+res['stderr'] if res['stderr'] else '')
    else:
        raise Exception(f"请求失败({res.status_code}):{res.text}")