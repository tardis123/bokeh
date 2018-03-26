import {Filter} from "./filter"
import * as p from "core/properties"
import {keys, values} from "core/util/object"
import {DataSource} from "../sources/data_source"
import {use_strict} from "core/util/string"

export namespace CustomJSFilter {
  export interface Attrs extends Filter.Attrs {
    args: {[key: string]: any}
    code: string
  }

  export interface Props extends Filter.Props {}
}

export interface CustomJSFilter extends CustomJSFilter.Attrs {}

export class CustomJSFilter extends Filter {

  properties: CustomJSFilter.Props

  constructor(attrs?: Partial<CustomJSFilter.Attrs>) {
    super(attrs)
  }

  static initClass(): void {
    this.prototype.type = 'CustomJSFilter'

    this.define({
      args: [ p.Any,    {} ], // TODO (bev) better type
      code: [ p.String, '' ],
    })
  }

  get names(): string[] {
    return keys(this.args)
  }

  get values(): any[] {
    return values(this.args)
  }

  get func(): Function {
    return new Function(...this.names, "source", "require", "exports", use_strict(this.code))
  }

  compute_indices(source: DataSource): number[] | null {
    this.filter = this.func(...this.values, source, require, {})
    return super.compute_indices(source)
  }
}
CustomJSFilter.initClass()
