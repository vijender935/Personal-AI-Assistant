import {describe,expect,it} from "vitest";
import {fileUrl} from "./useFiles";

describe("fileUrl",()=>{
 it("encodes every path segment",()=>{
  expect(fileUrl("https://api.test","docs/my file.pdf")).toBe("https://api.test/api/v1/files/docs/my%20file.pdf");
 });
 it("does not allow slashes inside a segment to alter the URL",()=>{
  expect(fileUrl("https://api.test","a/b c.txt")).toBe("https://api.test/api/v1/files/a/b%20c.txt");
 });
});
