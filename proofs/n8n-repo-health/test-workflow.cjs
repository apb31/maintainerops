const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const w = JSON.parse(fs.readFileSync(path.join(__dirname, 'workflow.json'), 'utf8'));
assert.equal(w.active, false);
assert.equal(w.nodes.length, 3);
assert.equal(w.nodes.some(n => n.credentials), false);
const http = w.nodes.find(n => n.type === 'n8n-nodes-base.httpRequest');
assert.equal(http.parameters.url, 'https://api.github.com/repos/apb31/maintainerops');
assert.equal(http.parameters.options.timeout, 15000);
assert.equal(http.maxTries, 3);
const names = new Set(w.nodes.map(n => n.name));
for (const [from, links] of Object.entries(w.connections)) {
  assert(names.has(from));
  for (const targets of links.main) for (const edge of targets) assert(names.has(edge.node));
}
const program = w.nodes.find(n => n.type === 'n8n-nodes-base.code').parameters.jsCode;
function run(json) {
  return vm.runInNewContext('(function(){' + program + '})()', {$input:{first:()=>({json})}}, {timeout:100});
}
const valid = {full_name:'apb31/maintainerops',stargazers_count:0,forks_count:1,open_issues_count:2};
assert.equal(run({statusCode:200,body:valid})[0].json.open_issues_and_prs, 2);
assert.equal(run({statusCode:429,body:{}})[0].json.retryable, true);
assert.equal(run({statusCode:503,body:{}})[0].json.ok, false);
assert.equal(run({statusCode:404,body:{}})[0].json.retryable, false);
assert.throws(()=>run({statusCode:200,body:{...valid,full_name:'other/repo'}}), /identity/);
assert.throws(()=>run({statusCode:200,body:{...valid,open_issues_count:-1}}), /Invalid count/);
assert.throws(()=>run({body:valid}), /Missing HTTP status/);
console.log('PASS: workflow structure + 7 Code-node fixture cases; n8n runtime NOT tested.');
